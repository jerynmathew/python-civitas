# Changelog

> **Note:** This project was renamed from Agency to Civitas in April 2026.
> Historical entries below refer to the product as "Agency".

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

#### M4.1 — HTTP Gateway

- `civitas.gateway.HTTPGateway` — supervised `AgentProcess` that translates HTTP ↔ Civitas messages; external clients never touch the bus directly
- `civitas.gateway.GatewayConfig` — dataclass covering host, port, TLS, HTTP/3 (QUIC), routes, middleware, OpenAPI docs, and request timeout
- `civitas.gateway.RouteTable` — ordered route matching table; path parameters extracted and merged into `message.payload`; YAML is the authoritative source
- `civitas.gateway.route` — `@route(method, path, mode=)` decorator to co-locate route metadata on agent methods; used by `civitas topology validate`, never read at runtime
- `civitas.gateway.contract` — `@contract(request=Model, response=Model)` decorator; wired to `RouteTable.merge_contracts_from()` for automatic 422/500 validation
- `civitas.gateway.GatewayRequest` / `GatewayResponse` — thin middleware types; middleware receives `(request, next_fn)` and can short-circuit or pass through
- Middleware chain: global middleware loaded from dotted import paths in `config.middleware`; per-route middleware supported in `RouteEntry`
- OpenAPI 3.1 spec auto-generated from route table; served at `GET /docs/openapi.json`; Swagger UI served at `GET /docs` (CDN-hosted, zero bundling)
- Default URL conventions: `POST /agents/{name}` → call, `POST /agents/{name}/cast` → cast, `GET /agents/{name}/state` → call with `{"__op__": "state"}`
- HTTP/3 / QUIC via `civitas[http3]` (`aioquic`): `H3Server` runs alongside uvicorn; `Alt-Svc` header injected automatically when `enable_http3: true`
- W3C `traceparent` header parsed and propagated to trace context; `X-Civitas-Type` header overrides the Civitas message type
- Topology YAML support: `type: http_gateway` node type wired into `Runtime._build_node()`; `civitas topology show` renders `[http]` prefix
- `examples/http_gateway.py` — end-to-end example with `EchoAgent` and Swagger UI
- `pyproject.toml` — `civitas[http]` (uvicorn + pydantic) and `civitas[http3]` (+ aioquic) optional extras

#### M4.3 — Codebase Security & Enterprise Posture

- `.github/workflows/security.yml` — three-job security CI workflow running on every PR and weekly:
  - SAST: Bandit (`-lll -iii`, HIGH+ severity) + Semgrep (`p/python`, `p/secrets`, `p/owasp-top-ten`); SARIF uploaded to GitHub Security tab
  - Dependency audit: `pip-audit --strict` against PyPI Advisory Database; fails on any fixable vulnerability
  - Secret scan: `gitleaks` on full git history (`fetch-depth: 0`)
- `.github/dependabot.yml` — weekly Dependabot scans for pip and GitHub Actions dependencies; dev-tools grouped to reduce PR noise
- `publish.yml` — CycloneDX SBOM generated (JSON + XML) on every release tag; attached as GitHub release assets
- `.pre-commit-config.yaml` — `gitleaks` pre-commit hook added; blocks secret commits before they reach the remote
- `SECURITY.md` — responsible disclosure policy: email contact, response SLAs (2 days ack, 14 days for CRITICAL/HIGH), 90-day coordinated disclosure window, CVE process, supported versions
- `docs/security/threat-model.md` — STRIDE analysis for all runtime components: `AgentProcess`, `Supervisor`, `MessageBus`, `ZMQTransport`, `NATSTransport`, `HTTPGateway`, `StateStore`, plugin system, `EvalAgent`; risk summary with 21 itemised threats
- `docs/security/architecture.md` — four-zone trust boundary model (runtime process → Worker processes → remote machines → external clients), transport security posture per level, credential handling patterns, planned M4.2 hardening roadmap
- `docs/security/enterprise-checklist.md` — tiered adoption checklist (Level 1–4 by deployment complexity) + compliance guidance for SOC 2, GDPR, and HIPAA

---

## [0.3.0] — 2026-04-22

### Added

#### M2.5 — EvalLoop

- `EvalAgent` — supervised process that monitors agent behaviour and sends correction signals; sits alongside regular agents in the supervision tree
- `EvalEvent` — observable event emitted by agents; schema aligned with OTEL GenAI Semantic Conventions for remote exporter compatibility
- `CorrectionSignal` — three severity levels: `nudge` (soft guidance), `redirect` (change course), `halt` (stop agent cleanly)
- `EvalExporter` protocol — interface for remote eval engine adapters (Arize, Fiddler, Langfuse, etc.); implementations in M2.6
- `AgentProcess.emit_eval(event_type, payload, eval_agent)` — emit an observable event; no-op when bus not wired (safe in tests)
- `AgentProcess.on_correction(message)` — override hook called on `civitas.eval.correction` signals (nudge / redirect)
- `civitas.eval.halt` message type — breaks target agent's message loop cleanly; `on_stop()` still runs
- Rate limiting on `EvalAgent`: sliding window per target agent (`max_corrections_per_window`, `window_seconds`); excess corrections dropped and logged
- `type: eval_agent` YAML shorthand in `Runtime.from_config()` with `max_corrections_per_window` and `window_seconds` config
- `[eval]` label in `print_tree()` / `civitas topology show` for EvalAgent nodes
- `EvalAgent`, `EvalEvent`, `CorrectionSignal`, `EvalExporter` exported from `civitas` top-level package

#### M3.5 — GenServer

- `GenServer` — OTP-style generic server process with `handle_call` (synchronous, reply required), `handle_cast` (fire-and-forget), and `handle_info` (timers, internal signals) dispatch
- `send_after(delay_ms, payload)` — schedules a `handle_info` message to self after a delay; pending tasks cancelled on stop
- `AgentProcess.call(name, payload)` — synchronous GenServer call (wraps `ask()`, returns payload dict)
- `AgentProcess.cast(name, payload)` — fire-and-forget GenServer cast
- `Runtime.call()` / `Runtime.cast()` — runtime-level GenServer messaging
- `GenServer` exported from `civitas` top-level package
- `type: gen_server` support in `Runtime.from_config()` YAML topology
- `[srv]` label in `print_tree()` / `civitas topology show` for GenServer nodes

#### M3.4 — MCP Integration

- `civitas[mcp]` optional extra (`pip install 'civitas[mcp]'`) — wraps `mcp>=1.0` SDK
- `MCPServerConfig` — config dataclass for stdio and SSE MCP server connections; validated at construction
- `MCPClient` — persistent-per-agent MCP session with `connect()`, `disconnect()`, `list_tools()`, `call_tool()`; `AsyncExitStack` manages transport + session lifecycle as a unit
- `MCPTool` — `ToolProvider` wrapping a single MCP tool; name follows `mcp://server_name/tool_name` URI scheme for direct lookup via `self.tools.get()`; emits `civitas.mcp.call` OTEL span
- `MCPToolError` — raised when an MCP tool call returns `isError=True`
- `AgentProcess.connect_mcp(config)` — connects to an MCP server and registers all its tools into `self.tools`; idempotent (disconnects and deregisters existing tools for the same server before reconnecting)
- `ToolRegistry.deregister_prefix(prefix)` — removes all tools whose name starts with a given prefix
- `mcp.servers` topology YAML key — declare MCP servers in the topology file; `Runtime.from_config()` parses configs and auto-connects all agents on `start()`
- MCP clients are closed gracefully in the `_message_loop` finally block alongside `on_stop()`

---

## [0.1.0] — 2026-04-06

Initial public release.

### Added

#### Core runtime

- `AgentProcess` — asyncio-based agent with bounded mailbox, lifecycle hooks (`on_start`, `handle`, `on_error`, `on_stop`), and injected dependencies (`self.llm`, `self.tools`, `self.store`, `self._tracer`)
- `Supervisor` — fault tolerance tree with three restart strategies: `ONE_FOR_ONE`, `ONE_FOR_ALL`, `REST_FOR_ONE`
- Configurable backoff policies: `CONSTANT`, `LINEAR`, `EXPONENTIAL` (with 25% jitter)
- Sliding-window restart rate limiting (`max_restarts` + `restart_window`)
- Escalation chain — supervisor that exceeds its restart limit escalates to its parent
- Heartbeat-based monitoring for agents running in remote Worker processes
- `Runtime` — assembles and manages the full supervision tree; 13-step deterministic startup sequence
- `Worker` — multi-process agent host; connects to the broker and announces agents via `_agency.register`
- `ComponentSet` — shared infrastructure wiring for both `Runtime` and `Worker`
- `Runtime.from_config()` — builds a complete runtime from a YAML topology file

#### Messaging

- `MessageBus` — name-based routing with Registry lookup and ephemeral reply address fallback
- `send()` — fire-and-forget delivery
- `ask()` — request-reply with configurable timeout and ephemeral reply routing
- `broadcast()` — glob-pattern delivery to multiple agents
- `reply()` — return a reply from `handle()` without knowing the caller's address
- Bounded mailboxes with `asyncio.QueueFull` backpressure
- System message namespace (`_agency.*`) reserved and validated at route time
- Trace context propagation across all message boundaries

#### Transport layer

- `InProcessTransport` — asyncio queues, zero extra dependencies, ~2–5 µs latency
- `ZMQTransport` — XSUB/XPUB proxy, multi-process on a single machine (`pip install civitas[zmq]`)
- `NATSTransport` — distributed multi-machine transport with optional JetStream durable subscriptions (`pip install civitas[nats]`)
- Uniform `Transport` protocol — swap transports with a one-line topology change, no agent code changes
- Remote agent registration/deregistration via `_agency.register` / `_agency.deregister` messages

#### Plugin system

- `ModelProvider` protocol — structural, no base class required
- `AnthropicProvider` — first-party Anthropic SDK integration with built-in token pricing (`pip install civitas[anthropic]`)
- `LiteLLMProvider` — 100+ models via LiteLLM (OpenAI, Gemini, Bedrock, Azure, etc.) (`pip install civitas[litellm]`)
- `ToolProvider` protocol and `ToolRegistry` — named tools with JSON schema, duplicate name detection
- `StateStore` protocol — `get` / `set` / `delete` by agent name
- `InMemoryStateStore` — default, in-process, survives supervisor restarts
- `SQLiteStateStore` — durable persistence, all I/O in thread executor (non-blocking)
- `ModelResponse` dataclass — content, model, token counts, cost, tool calls
- Plugin loading from YAML topology — entrypoint → built-in name → dotted import path resolution
- `PluginError` — fast-fail at `Runtime.start()` with actionable error messages and install hints

#### Observability

- Automatic OTEL spans for every message send/receive, agent lifecycle event, LLM call, tool invocation, and supervisor restart
- `SpanQueue` — non-blocking span emission from the message loop (`put_nowait`, drops oldest if full)
- Three output modes: built-in `logging.DEBUG` console output (no deps) → OTEL `ConsoleSpanExporter` → OTLP gRPC export (Jaeger, Grafana Tempo, Datadog, etc.)
- `llm_span()` and `tool_span()` context managers for custom instrumentation
- Full span attribute reference under `civitas.*`, `llm.*`, `tool.*` namespaces
- Trace context propagation across process and machine boundaries
- `FanOutBackend` — export to multiple backends simultaneously
- Per-agent LLM cost attribution via `llm.cost_usd` span attribute

#### Framework adapters

- `LangGraphAgent` — wraps a LangGraph `CompiledGraph` as an `AgentProcess`; optional typed `input_schema` for early payload validation
- `OpenAIAgent` — wraps an OpenAI Agents SDK `Agent`; maps handoffs to Civitas `send()` calls

#### YAML topology

- Declarative topology YAML — supervision tree, transport, plugins in one file
- Full field schema: supervision strategies, backoff, transport per-implementation config, plugin config
- Process affinity — `process: worker` assigns agents to named Worker processes
- `Runtime.from_config()` with short-name `agent_classes` map
- Flat agent shorthand (`agent: { name: ..., type: ... }`)
- Case-insensitive strategy and backoff values

#### CLI

- `civitas run` — start the runtime from a topology file; `--transport`, `--process`, `--nats-url` overrides
- `civitas topology validate` — structural and configuration validation with grouped output; exit 1 on failure (CI-safe)
- `civitas topology show` — render the supervision tree with inline restart policies
- `civitas topology diff` — meaningful diff between two topology files grouped by section
- `civitas deploy docker-compose` — generate `Dockerfile`, `docker-compose.yml`, and `.env` from a topology; one service per process group
- `civitas state list` / `show` / `clear` — inspect and manage persisted agent state

#### Serialization

- `MsgpackSerializer` — default, binary, fast
- `JsonSerializer` — human-readable, selectable via `AGENCY_SERIALIZER=json`
- All messages serialized even on InProcessTransport — guarantees transport-swap transparency
- `DeserializationError` with stable contract and schema versioning

### Changed

- `Registry` redesigned as `LocalRegistry` with `RoutingEntry` dataclass and glob-pattern `lookup_all()` for broadcast
- `ComponentSet` extracted from `Runtime` to eliminate wiring duplication between `Runtime` and `Worker`
- Backoff computation moved to `Supervisor._compute_backoff()` with explicit jitter on EXPONENTIAL
- Supervisor crash handling uses tracked `asyncio.Task` set (`_pending_crash_tasks`) to prevent races with shutdown
- Sliding window uses `collections.deque` for O(1) append/popleft; child lookup uses supplementary dict for O(1) by name

### Fixed

- ZMQ transport: idempotent `start()`, correct error handling on socket close, reply routing for cross-process messages
- NATS transport: reconnection handling, JetStream stream creation idempotency
- Supervisor: crash handler tasks are cancelled before children are stopped (`stop()` teardown ordering)
- Supervisor: `ONE_FOR_ALL` and `REST_FOR_ONE` skip agents already in `STOPPED` / `STOPPING` / `CRASHED` states
- `AgentProcess`: state restored from `StateStore` before `on_start()` runs on restart
- `MessageBus`: `_agency.*` message type validation applied to all routes, not just system senders
- `OpenAIAgent`: unregistered handoff targets log a warning rather than crashing the handler
- `LangGraphAgent`: non-dict graph outputs are wrapped in `{"output": value}` rather than raising `TypeError`
- Pre-commit hooks: ruff + mypy run on every commit; CI enforces 85% coverage threshold

[Unreleased]: https://github.com/jerynmathew/python-civitas/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/jerynmathew/python-civitas/compare/v0.1.0...v0.3.0
[0.1.0]: https://github.com/jerynmathew/python-civitas/releases/tag/v0.1.0
