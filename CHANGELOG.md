# Changelog

> **Note:** This project was renamed from Agency to Civitas in April 2026.
> Historical entries below refer to the product as "Agency".

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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

[Unreleased]: https://github.com/jerynmathew/python-civitas/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jerynmathew/python-civitas/releases/tag/v0.1.0
