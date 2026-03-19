"""Worker — lightweight process host for remote agents.

A Worker connects to an existing ZMQ proxy and hosts one or more agents.
It provides the same wiring as Runtime (bus, registry, tracer, serializer)
but without the supervision tree — supervision is handled remotely by the
Runtime process.

Usage from a subprocess:

    import asyncio
    from agency.worker import Worker
    from myagents import MyAgent

    async def main():
        worker = Worker(
            agents=[MyAgent("my_agent")],
            zmq_pub_addr="tcp://127.0.0.1:5559",
            zmq_sub_addr="tcp://127.0.0.1:5560",
        )
        await worker.start()
        await worker.wait_until_stopped()

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from agency.bus import MessageBus
from agency.messages import Message
from agency.observability.tracer import Tracer
from agency.process import AgentProcess, ProcessStatus
from agency.registry import Registry
from agency.serializer import MsgpackSerializer, Serializer
from agency.transport.zmq import ZMQTransport


class Worker:
    """Hosts agents in a worker process, connecting to an existing ZMQ proxy.

    The Worker provides:
    - ZMQ transport (connect-only, no proxy start)
    - Local registry and message bus
    - Heartbeat auto-response (handled by AgentProcess._message_loop)
    - Restart command handling (_agency.restart messages)
    """

    def __init__(
        self,
        agents: list[AgentProcess],
        zmq_pub_addr: str = "tcp://127.0.0.1:5559",
        zmq_sub_addr: str = "tcp://127.0.0.1:5560",
        serializer: Serializer | None = None,
        model_provider: Any = None,
        tool_registry: Any = None,
        state_store: Any = None,
    ) -> None:
        self._agents = agents
        self._zmq_pub_addr = zmq_pub_addr
        self._zmq_sub_addr = zmq_sub_addr
        self._custom_serializer = serializer
        self._model_provider = model_provider
        self._tool_registry = tool_registry
        self._state_store = state_store

        self._serializer: Serializer | None = None
        self._tracer: Tracer | None = None
        self._transport: ZMQTransport | None = None
        self._registry: Registry | None = None
        self._bus: MessageBus | None = None
        self._started = False
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the worker: connect to proxy, wire agents, start loops."""
        # Serializer
        if self._custom_serializer is not None:
            self._serializer = self._custom_serializer
        elif os.environ.get("AGENCY_SERIALIZER") == "json":
            from agency.serializer import JsonSerializer

            self._serializer = JsonSerializer()
        else:
            self._serializer = MsgpackSerializer()

        # Tracer
        self._tracer = Tracer()

        # Transport — connect to proxy, don't start one
        self._transport = ZMQTransport(
            self._serializer,
            pub_addr=self._zmq_pub_addr,
            sub_addr=self._zmq_sub_addr,
            start_proxy=False,
        )

        # Registry and bus
        self._registry = Registry()
        self._bus = MessageBus(
            transport=self._transport,
            registry=self._registry,
            serializer=self._serializer,
            tracer=self._tracer,
        )

        # State store
        if self._state_store is None:
            from agency.plugins.state import InMemoryStateStore

            self._state_store = InMemoryStateStore()

        # Wire agents
        for agent in self._agents:
            agent._bus = self._bus
            agent._tracer = self._tracer
            agent.llm = self._model_provider
            agent.tools = self._tool_registry
            agent.store = self._state_store
            self._registry.register(agent.name, agent)

        # Start transport
        await self._transport.start()

        # Subscribe agents
        for agent in self._agents:
            await self._bus.setup_agent(agent)

        # Wait for subscriptions to propagate
        await self._transport.wait_ready()

        # Subscribe to restart commands for this worker
        await self._transport.subscribe(
            "_agency.worker.restart", self._on_restart_command
        )

        # Start agent message loops
        for agent in self._agents:
            await agent._start()

        self._started = True

    async def _on_restart_command(self, data: bytes) -> None:
        """Handle restart commands from the supervisor."""
        assert self._serializer is not None
        msg = self._serializer.deserialize(data)
        target_name = msg.payload.get("agent_name", "")

        for agent in self._agents:
            if agent.name == target_name:
                # Stop the agent
                await agent._stop()
                # Re-initialize
                agent._status = ProcessStatus.INITIALIZING
                if self._registry is not None:
                    self._registry.deregister(agent.name)
                    self._registry.register(agent.name, agent)
                if self._bus is not None:
                    await self._bus.setup_agent(agent)
                # Restart
                await agent._start()
                break

    async def stop(self) -> None:
        """Stop all agents and disconnect from the proxy."""
        if not self._started:
            return

        for agent in reversed(self._agents):
            await agent._stop()

        if self._transport is not None:
            await self._transport.stop()

        if self._tracer is not None:
            self._tracer.flush()

        self._started = False
        self._stop_event.set()

    async def wait_until_stopped(self) -> None:
        """Block until stop() is called. Useful for long-running workers."""
        await self._stop_event.wait()

    @property
    def started(self) -> bool:
        return self._started
