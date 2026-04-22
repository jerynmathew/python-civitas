"""Runtime — wires components together, manages lifecycle."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, cast

import yaml

from civitas.components import ComponentSet, build_component_set
from civitas.errors import ConfigurationError
from civitas.evalloop import EvalAgent
from civitas.genserver import GenServer
from civitas.mcp.types import MCPServerConfig
from civitas.messages import Message, _new_span_id, _uuid7
from civitas.plugins.loader import load_plugins_from_config
from civitas.process import AgentProcess
from civitas.serializer import Serializer
from civitas.supervisor import Supervisor

logger = logging.getLogger(__name__)


class Runtime:
    """Assembles and manages the full Civitas runtime.

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
        components: ComponentSet | None = None,
    ) -> None:
        self._root_supervisor = supervisor
        self._transport_type = transport
        self._custom_serializer = serializer
        self._model_provider = model_provider
        self._tool_registry = tool_registry
        self._state_store = state_store
        self._components = components

        # ZMQ-specific config
        self._zmq_pub_addr = zmq_pub_addr
        self._zmq_sub_addr = zmq_sub_addr
        self._zmq_start_proxy = zmq_start_proxy

        # NATS-specific config
        self._nats_servers = nats_servers
        self._nats_jetstream = nats_jetstream
        self._nats_stream_name = nats_stream_name

        # MCP server configs parsed from topology YAML
        self._mcp_configs: list[Any] = []

        # Set during start() — exposed for stop(), ask()/send(), and get_agent()
        self._serializer: Serializer | None = None
        self._tracer: Any = None
        self._transport: Any = None
        self._registry: Any = None
        self._bus: Any = None
        self._agents_by_name: dict[str, AgentProcess] = {}  # F04-10: O(1) live process lookup
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
            try:
                module = importlib.import_module(module_path)
                return cast(type[AgentProcess], getattr(module, class_name))
            except (ImportError, AttributeError) as exc:
                raise ConfigurationError(
                    f"Cannot load agent type '{type_str}': {exc}. "
                    f"Check that the module is installed and the class name is correct."
                ) from exc

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
            elif node.get("type") == "eval_agent" and "name" in node:
                return EvalAgent(
                    name=node["name"],
                    max_corrections_per_window=node.get("max_corrections_per_window", 10),
                    window_seconds=node.get("window_seconds", 60.0),
                )
            elif "agent" in node:
                agent_cfg = node["agent"]
                agent_cls = _resolve_class(agent_cfg["type"])
                return agent_cls(name=agent_cfg["name"])
            elif (
                node.get("type") in ("gen_server", "agent") and "module" in node and "class" in node
            ):
                cls_path = f"{node['module']}.{node['class']}"
                agent_cls = _resolve_class(cls_path)
                return agent_cls(name=node["name"])
            elif "type" in node and "name" in node:
                # Flat dotted-path format: {type: "module.Class", name: "agent_name"}
                agent_cls = _resolve_class(node["type"])
                return agent_cls(name=node["name"])
            else:
                raise ValueError(f"Unknown node type in config: {node}")

        sup_cfg = config.get("supervision") or config.get("supervisor")
        if not sup_cfg:
            raise ConfigurationError("YAML topology must define a top-level 'supervision' key.")
        # Top-level is always a supervisor
        children = [_build_node(c) for c in sup_cfg.get("children", [])]
        root = Supervisor(
            name=sup_cfg.get("name", "root"),
            children=children,
            strategy=sup_cfg.get("strategy", "ONE_FOR_ONE").upper(),
            max_restarts=sup_cfg.get("max_restarts", 3),
            restart_window=sup_cfg.get("restart_window", 60.0),
            backoff=sup_cfg.get("backoff", "CONSTANT").upper(),
            backoff_base=sup_cfg.get("backoff_base", 1.0),
            backoff_max=sup_cfg.get("backoff_max", 60.0),
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
            loaded = load_plugins_from_config(config)
            if loaded["model_providers"]:
                if len(loaded["model_providers"]) > 1:
                    logger.warning(
                        "Multiple model providers found in YAML; using the first one. "
                        "Additional providers are ignored."
                    )
                kwargs["model_provider"] = loaded["model_providers"][0]
            if loaded["state_store"] is not None:
                kwargs["state_store"] = loaded["state_store"]

        runtime = cls(**kwargs)

        # MCP server config — parsed here, connected during start()
        mcp_section = config.get("mcp", {})
        if mcp_section.get("servers"):
            for srv in mcp_section["servers"]:
                runtime._mcp_configs.append(
                    MCPServerConfig(
                        name=srv["name"],
                        transport=srv["transport"],
                        command=srv.get("command"),
                        args=srv.get("args", []),
                        env=srv.get("env"),
                        url=srv.get("url"),
                    )
                )

        return runtime

    def all_agents(self) -> list[AgentProcess]:
        """Return all AgentProcess instances in the supervision tree."""
        if self._root_supervisor is None:
            return []
        return self._root_supervisor.all_agents()

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
                if isinstance(node, EvalAgent):
                    prefix_tag = "[eval]"
                elif isinstance(node, GenServer):
                    prefix_tag = "[srv]"
                else:
                    prefix_tag = "[agent]"
                label = f"{prefix_tag} {node.name} ({status})"
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

        # Steps 2–6: build or use provided ComponentSet.
        # Note: if a pre-built ComponentSet is provided, its transport must support
        # being started by this call — transport.start() is always called below. (F04-11)
        if self._components is not None:
            cs = self._components
        else:
            cs = build_component_set(
                transport_type=self._transport_type,
                serializer=self._custom_serializer,
                model_provider=self._model_provider,
                tool_registry=self._tool_registry,
                state_store=self._state_store,
                zmq_pub_addr=self._zmq_pub_addr,
                zmq_sub_addr=self._zmq_sub_addr,
                zmq_start_proxy=self._zmq_start_proxy,
                nats_servers=self._nats_servers,
                nats_jetstream=self._nats_jetstream,
                nats_stream_name=self._nats_stream_name,
            )

        # Expose on self for stop(), ask(), send(), and get_agent()
        self._serializer = cs.serializer
        self._tracer = cs.tracer
        self._transport = cs.transport
        self._registry = cs.registry
        self._bus = cs.bus
        self._state_store = cs.store

        if self._root_supervisor is None:
            self._started = True
            return

        # 8. Inject dependencies into all AgentProcesses
        all_agents = self._root_supervisor.all_agents()
        for agent in all_agents:
            cs.inject(agent)

        # Inject into supervisors (supervisor-specific wiring, not via ComponentSet)
        for sup in self._root_supervisor.all_supervisors():
            sup._bus = cs.bus
            sup._registry = cs.registry
            sup._tracer = cs.tracer

        # 9. Register all AgentProcesses in Registry; build O(1) name→process map (F04-10)
        for agent in all_agents:
            self._registry.register(agent.name)
        self._agents_by_name = {a.name: a for a in all_agents}

        # 10. Start Transport
        await self._transport.start()

        # Set up transport subscriptions for each agent
        for agent in all_agents:
            await self._bus.setup_agent(agent)

        # Subscribe to cross-process agent announcements from Worker processes.
        # Workers publish _agency.register on startup so this runtime's bus can
        # route messages to remote agents without a shared registry service.
        async def _on_remote_register(data: bytes) -> None:
            msg = cs.serializer.deserialize(data)
            name: str = msg.payload.get("name", "")
            if name:
                try:
                    self._registry.register_remote(name)
                except ValueError:
                    pass  # already registered locally — ignore

        async def _on_remote_deregister(data: bytes) -> None:
            msg = cs.serializer.deserialize(data)
            name: str = msg.payload.get("name", "")
            if name:
                entry = self._registry.lookup(name)
                if entry is not None and not entry.is_local:
                    self._registry.deregister(name)

        await self._transport.subscribe("_agency.register", _on_remote_register)
        await self._transport.subscribe("_agency.deregister", _on_remote_deregister)

        # Wait for subscriptions to propagate (ZMQ slow joiner mitigation)
        if hasattr(self._transport, "wait_ready"):
            await self._transport.wait_ready()

        # Connect MCP servers declared in topology YAML to all agents
        if self._mcp_configs:
            for agent in all_agents:
                for mcp_cfg in self._mcp_configs:
                    try:
                        await agent.connect_mcp(mcp_cfg)
                    except Exception as exc:
                        logger.warning(
                            "Failed to connect agent '%s' to MCP server '%s': %s",
                            agent.name,
                            mcp_cfg.name,
                            exc,
                        )

        # 11-12. Start supervision tree (supervisors start their children)
        await self._root_supervisor.start()

        # 13. Runtime is ready
        self._started = True

    async def stop(self) -> None:
        """Shutdown sequence: stop agents, transport, flush tracer."""
        if not self._started:
            return

        # 1. Stop supervision tree (sends shutdown, awaits on_stop for each agent)
        if self._root_supervisor is not None:
            await self._root_supervisor.stop()

        # 2. Stop Transport
        if self._transport is not None:
            await self._transport.stop()

        # 3. Close StateStore
        if self._state_store is not None and hasattr(self._state_store, "close"):
            await self._state_store.close()

        # 4. Flush Tracer
        if self._tracer is not None:
            self._tracer.flush()

        self._agents_by_name.clear()
        self._started = False

    # ------------------------------------------------------------------
    # Public API — process lookup, send, and ask
    # ------------------------------------------------------------------

    def get_agent(self, name: str) -> AgentProcess | None:
        """Return the live AgentProcess instance by name, or None.

        O(1) lookup via the agents-by-name dict built during start().
        Use this when you need to inspect process state (e.g. status).
        For routing messages use runtime.send/ask instead.
        """
        return self._agents_by_name.get(name)

    async def call(
        self,
        agent_name: str,
        payload: dict[str, Any],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Synchronous call to a GenServer. Blocks until reply or timeout."""
        reply = await self.ask(agent_name, payload, timeout=timeout)
        return reply.payload

    async def cast(self, agent_name: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget cast to a GenServer. Returns immediately."""
        await self.send(agent_name, {**payload, "__cast__": True})

    async def ask(
        self,
        agent_name: str,
        payload: dict[str, Any],
        timeout: float = 30.0,
        message_type: str = "message",
    ) -> Message:
        """Send a message to an agent and await a reply."""
        if self._bus is None or self._tracer is None:
            raise RuntimeError("Runtime not started")

        trace_id = self._tracer.new_trace_id()
        message = Message(
            type=message_type,
            sender="_runtime",
            recipient=agent_name,
            payload=payload,
            correlation_id=_uuid7(),
            trace_id=trace_id,
            span_id=_new_span_id(),
        )
        return cast(Message, await self._bus.request(message, timeout=timeout))

    async def send(
        self,
        agent_name: str,
        payload: dict[str, Any],
        message_type: str = "message",
    ) -> None:
        """Fire-and-forget: send a message to an agent."""
        if self._bus is None or self._tracer is None:
            raise RuntimeError("Runtime not started")

        trace_id = self._tracer.new_trace_id()
        message = Message(
            type=message_type,
            sender="_runtime",
            recipient=agent_name,
            payload=payload,
            trace_id=trace_id,
            span_id=_new_span_id(),
        )
        await self._bus.route(message)
