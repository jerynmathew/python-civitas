"""Worker — lightweight process host for remote agents.

A Worker connects to an existing transport broker (ZMQ proxy or NATS server)
and hosts one or more agents. It provides the same wiring as Runtime (bus,
registry, tracer, serializer) but without the supervision tree — supervision
is handled remotely by the Runtime process.

Usage from a subprocess:

    import asyncio
    from agency.worker import Worker
    from myagents import MyAgent

    # ZMQ worker
    worker = Worker(
        agents=[MyAgent("my_agent")],
        transport="zmq",
        zmq_pub_addr="tcp://127.0.0.1:5559",
        zmq_sub_addr="tcp://127.0.0.1:5560",
    )

    # NATS worker
    worker = Worker(
        agents=[MyAgent("my_agent")],
        transport="nats",
        nats_servers="nats://localhost:4222",
    )
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agency.bus import MessageBus
from agency.config import settings
from agency.observability.tracer import Tracer
from agency.plugins.state import InMemoryStateStore
from agency.process import AgentProcess, ProcessStatus
from agency.registry import LocalRegistry, Registry
from agency.serializer import JsonSerializer, MsgpackSerializer, Serializer

logger = logging.getLogger(__name__)


class Worker:
    """Hosts agents in a worker process, connecting to an existing broker.

    Supports ZMQ (connect to proxy) and NATS (connect to server) transports.

    The Worker provides:
    - Transport connectivity (ZMQ or NATS)
    - Local registry and message bus
    - Heartbeat auto-response (handled by AgentProcess._message_loop)
    - Restart command handling (_agency.restart messages)
    """

    def __init__(
        self,
        agents: list[AgentProcess],
        transport: str = "zmq",
        zmq_pub_addr: str = "tcp://127.0.0.1:5559",
        zmq_sub_addr: str = "tcp://127.0.0.1:5560",
        nats_servers: str | list[str] = "nats://localhost:4222",
        nats_jetstream: bool = False,
        serializer: Serializer | None = None,
        model_provider: Any = None,
        tool_registry: Any = None,
        state_store: Any = None,
        max_restarts: int = 3,
    ) -> None:
        self._transport_type = transport
        self._zmq_pub_addr = zmq_pub_addr
        self._zmq_sub_addr = zmq_sub_addr
        self._nats_servers = nats_servers
        self._nats_jetstream = nats_jetstream
        self._custom_serializer = serializer
        self._model_provider = model_provider
        self._tool_registry = tool_registry
        self._state_store = state_store
        self._max_restarts = max_restarts

        # O(1) agent lookup by name (F02-8)
        self._agents: dict[str, AgentProcess] = {a.name: a for a in agents}
        self._restart_counts: dict[str, int] = {a.name: 0 for a in agents}

        self._serializer: Serializer | None = None
        self._tracer: Tracer | None = None
        self._transport: Any = None
        self._registry: Registry | None = None
        self._bus: MessageBus | None = None
        self._started = False
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the worker: connect to proxy, wire agents, start loops."""
        # Serializer
        if self._custom_serializer is not None:
            self._serializer = self._custom_serializer
        elif settings.serializer == "json":
            self._serializer = JsonSerializer()
        else:
            self._serializer = MsgpackSerializer()

        # Tracer
        self._tracer = Tracer()

        # Transport — connect to existing broker
        if self._transport_type == "nats":
            from agency.transport.nats import NATSTransport

            self._transport = NATSTransport(
                self._serializer,
                servers=self._nats_servers,
                jetstream=self._nats_jetstream,
            )
        else:
            from agency.transport.zmq import ZMQTransport

            self._transport = ZMQTransport(
                self._serializer,
                pub_addr=self._zmq_pub_addr,
                sub_addr=self._zmq_sub_addr,
                start_proxy=False,
            )

        # Registry and bus
        self._registry = LocalRegistry()
        self._bus = MessageBus(
            transport=self._transport,
            registry=self._registry,
            serializer=self._serializer,
            tracer=self._tracer,
        )

        # State store
        if self._state_store is None:
            self._state_store = InMemoryStateStore()

        # Start transport first — must be running before setup_agent (F02-16)
        await self._transport.start()

        # Wait for subscriptions to propagate (ZMQ slow joiner)
        if hasattr(self._transport, "wait_ready"):
            await self._transport.wait_ready()

        # Wire and subscribe agents
        for agent in self._agents.values():
            self._wire_agent(agent)
            self._registry.register(agent.name)
            await self._bus.setup_agent(agent)

        # Subscribe to restart commands for this worker
        await self._transport.subscribe(
            "_agency.worker.restart", self._on_restart_command
        )

        # Start agent message loops
        for agent in self._agents.values():
            await agent._start()

        self._started = True

    def _wire_agent(self, agent: AgentProcess) -> None:
        """Inject dependencies into an agent."""
        agent._bus = self._bus
        agent._tracer = self._tracer
        agent.llm = self._model_provider
        agent.tools = self._tool_registry
        agent.store = self._state_store

    async def _on_restart_command(self, data: bytes) -> None:
        """Handle restart commands from the supervisor."""
        if self._serializer is None:
            raise RuntimeError("Worker not started")
        msg = self._serializer.deserialize(data)
        target_name = msg.payload.get("agent_name", "")

        agent = self._agents.get(target_name)
        if agent is None:
            logger.warning("Worker: restart command for unknown agent %r", target_name)
            return

        restart_count = self._restart_counts.get(target_name, 0)
        if restart_count >= self._max_restarts:
            logger.error(
                "Worker: agent %r exceeded max_restarts (%d), not restarting",
                target_name, self._max_restarts,
            )
            return

        try:
            await agent._stop()
            agent._status = ProcessStatus.INITIALIZING
            if self._registry is not None:
                self._registry.deregister(agent.name)
                self._registry.register(agent.name)
            if self._bus is not None:
                await self._bus.setup_agent(agent)
            await agent._start()
            self._restart_counts[target_name] = restart_count + 1
            logger.info(
                "Worker: restarted agent %r (attempt %d/%d)",
                target_name, self._restart_counts[target_name], self._max_restarts,
            )
        except Exception:
            logger.exception("Worker: failed to restart agent %r", target_name)

    async def stop(self) -> None:
        """Stop all agents and disconnect from the proxy."""
        if not self._started:
            return

        for agent in reversed(list(self._agents.values())):
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
