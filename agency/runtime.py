"""Runtime — wires components together, manages lifecycle."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

from agency.bus import MessageBus
from agency.config import settings
from agency.messages import Message, _uuid7
from agency.observability.tracer import Tracer, _new_span_id
from agency.process import AgentProcess
from agency.registry import Registry
from agency.serializer import JsonSerializer, MsgpackSerializer, Serializer
from agency.supervisor import Supervisor
from agency.transport.inprocess import InProcessTransport


class Runtime:
    """Assembles and manages the full Agency runtime.

    Startup sequence (from Implementation Guide §3):
    1. Read configuration
    2. Create Serializer
    3. Create Tracer
    4. Create Transport
    5. Create Registry
    6. Create MessageBus
    7. Create plugin instances
    8. Instantiate / wire all AgentProcesses
    9. Register all AgentProcesses in Registry
    10. Start Transport
    11. Walk supervision tree bottom-up, start each agent
    12. Start all Supervisors
    13. Runtime is ready
    """

    def __init__(
        self,
        supervisor: Supervisor | None = None,
        transport: str = "in_process",
        serializer: Serializer | None = None,
        model_provider: Any = None,
        tool_registry: Any = None,
        state_store: Any = None,
        zmq_pub_addr: str = "tcp://127.0.0.1:5559",
        zmq_sub_addr: str = "tcp://127.0.0.1:5560",
        zmq_start_proxy: bool = True,
        nats_servers: str | list[str] = "nats://localhost:4222",
        nats_jetstream: bool = False,
        nats_stream_name: str = "AGENCY",
    ) -> None:
        self._root_supervisor = supervisor
        self._transport_type = transport
        self._custom_serializer = serializer
        self._model_provider = model_provider
        self._tool_registry = tool_registry
        self._state_store = state_store

        # ZMQ-specific config
        self._zmq_pub_addr = zmq_pub_addr
        self._zmq_sub_addr = zmq_sub_addr
        self._zmq_start_proxy = zmq_start_proxy

        # NATS-specific config
        self._nats_servers = nats_servers
        self._nats_jetstream = nats_jetstream
        self._nats_stream_name = nats_stream_name

        # Built during start()
        self._serializer: Serializer | None = None
        self._tracer: Tracer | None = None
        self._transport: Any = None  # Transport protocol (InProcess or ZMQ)
        self._registry: Registry | None = None
        self._bus: MessageBus | None = None
        self._started = False

    @classmethod
    def from_config(
        cls,
        path: str | Path,
        agent_classes: dict[str, type[AgentProcess]] | None = None,
    ) -> Runtime:
        """Build a Runtime from a YAML topology file.

        The ``agent_classes`` dict maps type strings (e.g. "MyAgent") to the
        actual Python class. If not provided, types are resolved via
        ``importlib`` from dotted module paths (e.g. "myapp.agents.MyAgent").
        """
        config = yaml.safe_load(Path(path).read_text())
        classes = agent_classes or {}

        def _resolve_class(type_str: str) -> type[AgentProcess]:
            if type_str in classes:
                return classes[type_str]
            # Try dotted import path: "myapp.agents.MyAgent"
            module_path, _, class_name = type_str.rpartition(".")
            if not module_path:
                raise ValueError(
                    f"Cannot resolve agent type '{type_str}'. "
                    f"Provide it in agent_classes or use a dotted path."
                )
            module = importlib.import_module(module_path)
            return getattr(module, class_name)

        def _build_node(node: dict[str, Any]) -> AgentProcess | Supervisor:
            if "supervisor" in node:
                sup_cfg = node["supervisor"]
                children = [_build_node(c) for c in sup_cfg.get("children", [])]
                return Supervisor(
                    name=sup_cfg["name"],
                    children=children,
                    strategy=sup_cfg.get("strategy", "ONE_FOR_ONE").upper(),
                    max_restarts=sup_cfg.get("max_restarts", 3),
                    restart_window=sup_cfg.get("restart_window", 60.0),
                    backoff=sup_cfg.get("backoff", "CONSTANT").upper(),
                    backoff_base=sup_cfg.get("backoff_base", 1.0),
                    backoff_max=sup_cfg.get("backoff_max", 60.0),
                )
            elif "agent" in node:
                agent_cfg = node["agent"]
                agent_cls = _resolve_class(agent_cfg["type"])
                return agent_cls(name=agent_cfg["name"])
            elif "type" in node and "name" in node:
                # Flat format: {type: "module.Class", name: "agent_name"}
                agent_cls = _resolve_class(node["type"])
                return agent_cls(name=node["name"])
            else:
                raise ValueError(f"Unknown node type in config: {node}")

        sup_cfg = config.get("supervision", config.get("supervisor", {}))
        # Top-level is always a supervisor
        children = [_build_node(c) for c in sup_cfg.get("children", [])]
        root = Supervisor(
            name=sup_cfg.get("name", "root"),
            children=children,
            strategy=sup_cfg.get("strategy", "ONE_FOR_ONE").upper(),
            max_restarts=sup_cfg.get("max_restarts", 3),
            restart_window=sup_cfg.get("restart_window", 60.0),
            backoff=sup_cfg.get("backoff", "CONSTANT").upper(),
        )

        # Transport config
        transport_cfg = config.get("transport", {})
        transport_type = transport_cfg.get("type", "in_process")

        kwargs: dict[str, Any] = {"supervisor": root, "transport": transport_type}
        if transport_type == "zmq":
            if "pub_addr" in transport_cfg:
                kwargs["zmq_pub_addr"] = transport_cfg["pub_addr"]
            if "sub_addr" in transport_cfg:
                kwargs["zmq_sub_addr"] = transport_cfg["sub_addr"]
            if "start_proxy" in transport_cfg:
                kwargs["zmq_start_proxy"] = transport_cfg["start_proxy"]
        elif transport_type == "nats":
            if "servers" in transport_cfg:
                kwargs["nats_servers"] = transport_cfg["servers"]
            if "jetstream" in transport_cfg:
                kwargs["nats_jetstream"] = transport_cfg["jetstream"]
            if "stream_name" in transport_cfg:
                kwargs["nats_stream_name"] = transport_cfg["stream_name"]

        # Plugin config
        if "plugins" in config:
            from agency.plugins.loader import load_plugins_from_config

            loaded = load_plugins_from_config(config)
            if loaded["model_providers"]:
                # Use first model provider as the primary
                kwargs["model_provider"] = loaded["model_providers"][0]
            if loaded["state_store"] is not None:
                kwargs["state_store"] = loaded["state_store"]

        return cls(**kwargs)

    def print_tree(self) -> str:
        """Return an ASCII representation of the supervision tree."""
        if self._root_supervisor is None:
            return "(no supervision tree)"

        lines: list[str] = []

        def _walk(node: Supervisor | AgentProcess, prefix: str, is_last: bool) -> None:
            connector = "└── " if is_last else "├── "
            if isinstance(node, Supervisor):
                label = f"[sup] {node.name} ({node.strategy.value})"
            else:
                status = node.status.value if hasattr(node, "status") else "?"
                label = f"{node.name} ({status})"
            lines.append(f"{prefix}{connector}{label}")

            if isinstance(node, Supervisor):
                child_prefix = prefix + ("    " if is_last else "│   ")
                for i, child in enumerate(node.children):
                    _walk(child, child_prefix, i == len(node.children) - 1)

        # Root
        root = self._root_supervisor
        lines.append(f"[sup] {root.name} ({root.strategy.value})")
        for i, child in enumerate(root.children):
            _walk(child, "", i == len(root.children) - 1)

        return "\n".join(lines)

    async def start(self) -> None:
        """Start the runtime following the canonical initialization sequence."""
        if self._started:
            return

        # 1. Configuration is already read (constructor args)

        # 2. Create Serializer
        if self._custom_serializer is not None:
            self._serializer = self._custom_serializer
        elif settings.serializer == "json":
            self._serializer = JsonSerializer()
        else:
            self._serializer = MsgpackSerializer()

        # 3. Create Tracer
        self._tracer = Tracer()

        # 4. Create Transport
        if self._transport_type == "zmq":
            from agency.transport.zmq import ZMQTransport

            self._transport = ZMQTransport(
                self._serializer,
                pub_addr=self._zmq_pub_addr,
                sub_addr=self._zmq_sub_addr,
                start_proxy=self._zmq_start_proxy,
            )
        elif self._transport_type == "nats":
            from agency.transport.nats import NATSTransport

            self._transport = NATSTransport(
                self._serializer,
                servers=self._nats_servers,
                jetstream=self._nats_jetstream,
                stream_name=self._nats_stream_name,
            )
        else:
            self._transport = InProcessTransport(self._serializer)

        # 5. Create Registry
        self._registry = Registry()

        # 6. Create MessageBus
        self._bus = MessageBus(
            transport=self._transport,
            registry=self._registry,
            serializer=self._serializer,
            tracer=self._tracer,
        )

        if self._root_supervisor is None:
            self._started = True
            return

        # 7. Create plugin instances (use provided or defaults)
        if self._state_store is None:
            from agency.plugins.state import InMemoryStateStore

            self._state_store = InMemoryStateStore()

        # 8. Inject dependencies into all AgentProcesses
        all_agents = self._root_supervisor.all_agents()
        for agent in all_agents:
            agent._bus = self._bus
            agent._tracer = self._tracer
            agent.llm = self._model_provider
            agent.tools = self._tool_registry
            agent.store = self._state_store

        # Inject into supervisors
        for sup in self._root_supervisor.all_supervisors():
            sup._bus = self._bus
            sup._registry = self._registry
            sup._tracer = self._tracer

        # 9. Register all AgentProcesses in Registry
        for agent in all_agents:
            self._registry.register(agent.name, agent)

        # 10. Start Transport
        await self._transport.start()

        # Set up transport subscriptions for each agent
        for agent in all_agents:
            await self._bus.setup_agent(agent)

        # Wait for subscriptions to propagate (ZMQ slow joiner mitigation)
        if hasattr(self._transport, "wait_ready"):
            await self._transport.wait_ready()

        # 11-12. Start supervision tree (supervisors start their children)
        await self._root_supervisor.start()

        # 13. Runtime is ready
        self._started = True

    async def stop(self) -> None:
        """Shutdown sequence: stop agents, transport, flush tracer."""
        if not self._started:
            return

        # 1-2. Stop supervision tree (sends shutdown, awaits on_stop)
        if self._root_supervisor is not None:
            await self._root_supervisor.stop()

        # 4. Stop Transport
        if self._transport is not None:
            await self._transport.stop()

        # 5. Close StateStore
        if self._state_store is not None and hasattr(self._state_store, "close"):
            await self._state_store.close()

        # 6. Flush Tracer
        if self._tracer is not None:
            self._tracer.flush()

        self._started = False

    # ------------------------------------------------------------------
    # Public API — send and ask from outside the agent tree
    # ------------------------------------------------------------------

    async def ask(
        self, agent_name: str, payload: dict[str, Any], timeout: float = 30.0
    ) -> Message:
        """Send a message to an agent and await a reply."""
        if self._bus is None or self._tracer is None:
            raise RuntimeError("Runtime not started")

        trace_id = self._tracer.new_trace_id()
        message = Message(
            type=payload.get("type", "message"),
            sender="_runtime",
            recipient=agent_name,
            payload=payload,
            correlation_id=_uuid7(),
            trace_id=trace_id,
            span_id=_new_span_id(),
        )
        return await self._bus.request(message, timeout=timeout)

    async def send(self, agent_name: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget: send a message to an agent."""
        if self._bus is None or self._tracer is None:
            raise RuntimeError("Runtime not started")

        trace_id = self._tracer.new_trace_id()
        message = Message(
            type=payload.get("type", "message"),
            sender="_runtime",
            recipient=agent_name,
            payload=payload,
            trace_id=trace_id,
            span_id=_new_span_id(),
        )
        await self._bus.route(message)
