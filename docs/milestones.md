# Milestones

Development progress across all phases of Civitas.

---

## Status legend

| Symbol | Status |
|--------|--------|
| ✅ | Completed |
| 🔄 | In Progress |
| ⏳ | Planned |
| ⏸️ | Deferred |
| 💡 | Idea — to be specced |

---

## Overview

| Phase | Milestone | Status | Completed |
|-------|-----------|--------|-----------|
| 1 | [Core Runtime](#phase-1-core-runtime) | ✅ Completed | Mar 2026 |
| 2 | [Ecosystem — Transports](#m21-zmq-multi-process-transport) | ✅ Completed | Mar 2026 |
| 2 | [Ecosystem — Observability](#m23-otel-observability) | ✅ Completed | Apr 2026 |
| 2 | [Ecosystem — EvalLoop](#m25-evalloop) | ⏳ Planned | v0.3 |
| 3 | [Developer Experience — CLI & Dashboard](#phase-3-developer-experience) | ✅ Completed | Mar 2026 |
| 3 | [Developer Experience — MCP Integration](#m34-mcp-integration) | ⏳ Planned | v0.3 |
| 3 | [Developer Experience — GenServer](#m35-genserver) | ⏳ Planned | v0.3 |
| — | [Infrastructure & Release](#infrastructure--release) | ✅ Completed | Apr 2026 |
| 4 | [Dynamic Agent Spawning](#m41b-dynamic-agent-spawning) | ⏳ Planned | v0.4 |
| 4 | [Security Hardening](#m42-security-hardening) | ⏳ Planned | v0.4 |
| 4 | [Capability-Aware Registry](#m44-capability-aware-registry) | ⏳ Planned | v0.5 |
| 4 | [HTTP Gateway](#http-gateway) | ⏳ Planned | v0.4 |
| 4 | [Gateway API Surface](#gateway-api-surface) | ⏳ Planned | v0.4 |
| 4 | [Postgres StateStore + Migration](#postgres-statestore--migration) | 💡 Idea | v0.4 |
| 4 | [Visual Topology Editor](#m41-visual-topology-editor) | ⏸️ Deferred | — |
| 5 | [Prompt Library & Playground](#prompt-library--playground) | 💡 Idea | v0.5+ |
| 5 | [LLM Gateway](#llm-gateway) | 💡 Idea | v0.5+ |
| 5 | [Fabrica — Tools Gateway](#fabrica--tools-gateway) | 💡 Idea | v0.5+ |
| 5 | [Skills Gateway](#skills-gateway) | 💡 Idea | v0.5+ |

---

## Phase 1 — Core Runtime

**Status: ✅ Completed — March 2026**

| # | Deliverable | Priority | Status |
|---|-------------|----------|--------|
| M1.1 | `AgentProcess` base class, mailbox, `handle()` lifecycle | 🔴 High | ✅ |
| M1.2 | `Supervisor` with `ONE_FOR_ONE`, `ONE_FOR_ALL`, `REST_FOR_ONE` strategies | 🔴 High | ✅ |
| M1.3 | Backoff policies (`CONSTANT`, `LINEAR`, `EXPONENTIAL`), restart windows, crash timestamps | 🔴 High | ✅ |
| M1.4 | `Serializer` with msgpack + schema versioning; `DeserializationError` contract | 🔴 High | ✅ |
| M1.5 | `InProcessTransport` + `MessageBus` routing; request-reply with ephemeral topics | 🔴 High | ✅ |
| M1.6 | `StateStore` protocol; SQLite plugin; state persistence across restarts | 🟡 Medium | ✅ |
| M1.7 | Plugin system; LLM providers (Anthropic, OpenAI, Gemini, Mistral, LiteLLM) | 🔴 High | ✅ |
| M1.8 | Personal AI Assistant demo (Telegram gateway + skill agents) | 🟡 Medium | ⏸️ Deferred |

---

## Phase 2 — Ecosystem

### M2.1 — ZMQ Multi-Process Transport

**Status: ✅ Completed — March 2026**

| Deliverable | Status |
|-------------|--------|
| `ZMQTransport` with XSUB/XPUB proxy | ✅ |
| `ZMQProxy` daemon thread | ✅ |
| PUB/SUB bridging across OS processes | ✅ |
| Request-reply over ephemeral topics | ✅ |
| `Worker` process class for multi-process deployment | ✅ |

---

### M2.2 — NATS Distributed Transport

**Status: ✅ Completed — March 2026**

| Deliverable | Status |
|-------------|--------|
| `NATSTransport` with JetStream support | ✅ |
| At-least-once delivery via durable consumers | ✅ |
| Multi-machine deployment support | ✅ |
| Worker multi-transport handoff | ✅ |

---

### M2.3 — OTEL Observability

**Status: ✅ Completed — April 2026**

| Deliverable | Status |
|-------------|--------|
| `Tracer` with automatic span generation per message | ✅ |
| `SpanQueue` with overflow protection | ✅ |
| `OTELAgent` batch exporter with configurable flush interval | ✅ |
| `ConsoleBackend` and `FanOutBackend` | ✅ |
| OTLP gRPC exporter plugin | ✅ |
| Trace propagation across agents (trace_id, parent_span_id) | ✅ |

---

### M2.5 — EvalLoop

**Status: ⏳ Planned — v0.3 | Priority: 🔴 High**

Corrective observability loop: an `EvalAgent` subclass monitors agent behaviour and injects correction signals back into running agents.

| Deliverable | Status |
|-------------|--------|
| `civitas/evalloop.py` — `EvalAgent` base class | ⏳ |
| `CorrectionSignal` message type with severity levels (nudge / redirect / halt) | ⏳ |
| Rate limiting (`max_corrections_per_window`) | ⏳ |
| YAML-configurable eval strategies | ⏳ |
| Integration tests | ⏳ |

---

## Phase 3 — Developer Experience

### M3.1–M3.3 — CLI and Dashboard

**Status: ✅ Completed — March 2026**

| Deliverable | Status |
|-------------|--------|
| `civitas init` project scaffolding | ✅ |
| `civitas run` supervisor + worker modes | ✅ |
| `civitas topology validate / show / diff` | ✅ |
| `civitas deploy docker-compose` generation | ✅ |
| `civitas state list / clear` | ✅ |
| `civitas dashboard` live terminal dashboard | ✅ |

---

### M3.4 — MCP Integration

**Status: ⏳ Planned — v0.3 | Priority: 🔴 High**

MCP protocol plumbing — the wire layer between Civitas agents and MCP tool servers. Agents call tools by direct address (`mcp://server/tool`); the runtime handles handshake, transport, schema negotiation, and tracing. Agents also expose themselves as MCP servers so external LLM clients can discover and call them.

**Scope:** protocol only. Tool discovery (finding the right tool from a large set without passing all schemas to the LLM) is intentionally deferred — it depends on a global ToolStore (M4.4) and is the core concern of Fabrica (civitas-forge).

**Dependency chain:** M3.4 → M4.4 (ToolStore) → Fabrica (retrieval)

| Deliverable | Status |
|-------------|--------|
| `self.tools.get("mcp://server/tool")` — direct-addressed tool call on `AgentProcess` | ⏳ |
| Automatic MCP handshake, transport, and schema negotiation (JSON-RPC 2.0) | ⏳ |
| Tool registration into agent `ToolRegistry` on MCP connect — seeds M4.4 ToolStore | ⏳ |
| Agents expose themselves as MCP tool servers (`list_tools`, `call_tool`) | ⏳ |
| MCP tool calls appear in OTEL traces as tool spans | ⏳ |
| Connection pooling with circuit breakers | ⏳ |
| ≥ 10 unit tests + ≥ 2 integration tests | ⏳ |

**Explicitly out of scope for M3.4:**
- Semantic or keyword tool retrieval (`find_tools`) — Fabrica
- Unified cross-agent tool namespace — M4.4 ToolStore
- Per-agent credential isolation for tool sources — M4.2 Security Hardening

---

### M3.5 — GenServer

**Status: ⏳ Planned — v0.3 | Priority: 🔴 High**

OTP-style generic server primitive for separating stateful API/RPC service processes from AI agent processes on the message bus. See [design spec](design/genserver.md).

| Deliverable | Status |
|-------------|--------|
| `GenServer` base class with `handle_call` / `handle_cast` / `handle_info` dispatch | ⏳ |
| `call()` — synchronous request-reply with timeout | ⏳ |
| `cast()` — async fire-and-forget | ⏳ |
| `send_after()` — delayed self-message (tick / timer support) | ⏳ |
| `init()` — startup initialisation hook | ⏳ |
| Supervision-compatible (works as a child of any `Supervisor`) | ⏳ |
| Topology YAML support (`type: gen_server`) | ⏳ |
| Unit tests (≥ 15 cases) | ⏳ |
| Documentation + examples | ⏳ |

---

## Infrastructure & Release

**Status: ✅ Completed — April 2026**

| Deliverable | Status | Completed |
|-------------|--------|-----------|
| Agency → Civitas rename (115 files) | ✅ | Apr 2026 |
| Pre-commit hooks (ruff, mypy, file hygiene) | ✅ | Apr 2026 |
| GitHub Actions CI (Python 3.12 / 3.13 / 3.14) | ✅ | Apr 2026 |
| PyPI publishing via OIDC trusted publishing | ✅ | Apr 2026 |
| GitHub Pages documentation site | ✅ | Apr 2026 |
| Test coverage raised from 85% → 90%+ | ✅ | Apr 2026 |
| Framework adapters: LangGraph, OpenAI Agents SDK | ✅ | Mar 2026 |
| Framework adapters: CrewAI | ⏳ | — |

---

## Phase 4 — Platform Maturation

### M4.1b — Dynamic Agent Spawning

**Status: ⏳ Planned — v0.4 | Priority: 🔴 High**

Agents spawn and decommission other agents at runtime. Enables LLM-driven orchestrators that create specialist agents on demand.

| Deliverable | Status |
|-------------|--------|
| `self.spawn(agent_class, name, ...)` on `AgentProcess` | ⏳ |
| Spawned agents registered with parent lineage in supervision tree | ⏳ |
| `self.despawn(name)` — clean decommission with state cleanup | ⏳ |
| `on_spawn_requested` governance hook | ⏳ |
| `max_concurrent_children` blast radius limit | ⏳ |
| Topology YAML round-trip (spawned agents reflected in `topology show`) | ⏳ |

---

### M4.2 — Security Hardening

**Status: ⏳ Planned — v0.4 | Priority: 🔴 High**

| Deliverable | Status |
|-------------|--------|
| mTLS for all inter-agent communication (ZMQ + NATS) | ⏳ |
| Message signing with tamper detection | ⏳ |
| Credential isolation (agents cannot access other agents' secrets) | ⏳ |
| Secret injection via environment / mounted secrets (not YAML) | ⏳ |
| Sandboxed tool execution with filesystem isolation | ⏳ |
| Audit log: all events logged with agent identity | ⏳ |

---

### M4.4 — Capability-Aware Registry

**Status: ⏳ Planned — v0.5 | Priority: 🟡 Medium**

Agents and LLMs discover capabilities at runtime — no pre-wiring needed.

| Deliverable | Status |
|-------------|--------|
| `AgentCardStore`: auto-generated from `@agent` decorator, queryable by skill / input type / tags | ⏳ |
| `ToolStore`: unified registry replacing per-agent `ToolRegistry` | ⏳ |
| `@agent(expose_as_tool=True)` — agent-as-tool | ⏳ |
| `KeywordBackend` (default) and `LocalEmbedBackend` (`civitas[search]`) | ⏳ |
| Schema versioning (semver) with forward compatibility | ⏳ |
| 25+ test cases covering all registry operations | ⏳ |

---

### HTTP Gateway

**Status: ⏳ Planned — v0.4 | Priority: 🔴 High**

Supervised edge process bridging external HTTP/gRPC traffic into the Civitas message bus. See [design spec](design/http-gateway.md).

| Deliverable | Status |
|-------------|--------|
| `HTTPGateway(AgentProcess)` — ASGI app, request translation, route table | ⏳ |
| HTTP/1.1 + HTTP/2 via uvicorn[standard] — uvloop + httptools (`civitas[http]`) | ⏳ |
| HTTP/3 / QUIC via aioquic — `Alt-Svc` header, 0-RTT (`civitas[http3]`) | ⏳ |
| gRPC via grpclib (`civitas[grpc]`) + grpcio C core (`civitas[grpc-fast]`) | ⏳ |
| Custom `.proto` loading from `proto_dir` | ⏳ |
| TLS config from `settings` / topology YAML / env vars | ⏳ |
| Topology YAML support (`type: http_gateway`) | ⏳ |
| Graceful drain on supervisor shutdown | ⏳ |
| ≥ 20 unit tests + ≥ 5 integration tests | ⏳ |
| Documentation + examples for all four protocols | ⏳ |

---

### Gateway API Surface

**Status: ⏳ Planned — v0.4 | Priority: 🔴 High**

Minimal integration surface on top of HTTPGateway: declarative routes, Pydantic request/response validation, middleware chain, and auto-generated OpenAPI docs. See [design spec](design/gateway-api-surface.md).

| Deliverable | Status |
|-------------|--------|
| `@route` decorator — maps GenServer method to HTTP method + path | ⏳ |
| Path parameter extraction into `message.payload` | ⏳ |
| `@contract` decorator — Pydantic request/response validation, 422 error shape | ⏳ |
| `GatewayRequest` / `GatewayResponse` middleware types | ⏳ |
| Global + route-scoped middleware chain | ⏳ |
| Stateful GenServer middleware support | ⏳ |
| Auto-generated OpenAPI 3.1 spec at `GET /openapi.json` | ⏳ |
| Swagger UI at `GET /docs`, ReDoc at `GET /redoc` | ⏳ |
| YAML-declared routes and schemas (no decorators required) | ⏳ |
| ≥ 15 unit tests + ≥ 3 integration tests | ⏳ |

---

### Postgres StateStore + Migration

**Status: 💡 Idea — to be specced | Priority: 🔴 High**

SQLite works for single-process deployments (Level 1) but breaks under concurrent cross-process writes (ZMQ Level 2+, NATS Level 3). `PostgresStateStore` extends the existing `StateStore` protocol — switching backends is a topology YAML change with no agent code changes. `civitas state migrate` handles moving existing state between backends with a dry-run mode.

The spec needs to resolve: connection pool sizing, schema compatibility guarantees between backends, whether migration supports live (dual-write) or maintenance-window-only mode, and PgBouncer integration for high-concurrency deployments.

| Idea | Notes |
|------|-------|
| `PostgresStateStore` plugin — same `StateStore` protocol, asyncpg backend | `civitas[postgres]` extra |
| Backend swap via topology YAML — no agent code changes | `backend: postgres`, `url: !ENV DATABASE_URL` |
| Connection pool config — pool size, max overflow, timeout | Configurable in topology YAML |
| `civitas state migrate --from sqlite:... --to postgres://...` | Dry-run by default; `--execute` to apply |
| Schema compatibility — identical key-value layout across backends | Migration is a straight copy, no transformation |
| Maintenance-window migration (stop → copy → restart) | Supported in v0.4 |
| Zero-downtime migration (dual-write + drain) | Deferred — complex; only needed for critical state |
| PgBouncer integration notes in deployment guide | Connection pooler config for high-concurrency deployments |
| Spec | design/postgres-statestore.md — to be written |

---

### M4.1 — Visual Topology Editor

**Status: ⏸️ Deferred | Priority: 🟢 Low**

Web-based drag-and-drop editor for designing agent topologies visually.

| Deliverable | Status |
|-------------|--------|
| Drag-and-drop agent/supervisor canvas | ⏸️ |
| Visual message flow connections | ⏸️ |
| Supervision strategy configuration via UI | ⏸️ |
| Export to valid Civitas topology YAML | ⏸️ |
| Round-trip: imported YAML renders correctly | ⏸️ |

---

## Phase 5 — Agentic Platform

Ideas awaiting full design specs. Each is a supervised GenServer (or group of GenServers) that runs inside the user's deployment — not external services, not SaaS. The SaaS boundary sits above these: hosted registries, managed observability, and multi-tenant governance are separate concerns.

---

### Prompt Library & Playground

**Status: 💡 Idea — to be specced | Priority: 🔴 High**

Prompts as first-class versioned entities, stored and served by a supervised `PromptStore(GenServer)`. Agents load instructions by name rather than hardcoding strings — prompt changes never require a code deploy. The playground (CLI + dashboard tab) lets you test a prompt version against a live agent before promoting it.

This is one of the strongest SaaS upgrade stories: the OSS `PromptStore` runs in your deployment; a hosted version adds a web UI for non-engineers, team collaboration, cross-deployment promotion, and output analytics.

| Idea | Notes |
|------|-------|
| `PromptStore(GenServer)` — versioned prompt storage on the bus | Agents call `call("prompt_store", {"agent": "assistant", "slot": "system"})` |
| SQLite backend (runtime-mutable) + YAML dir backend (git-tracked) | User chooses per deployment |
| Named version aliases — `latest`, `stable`, `experimental` | Pinned per agent per environment in topology YAML |
| Per-agent, per-slot prompt mapping | Each agent can have multiple slots: `system`, `few_shot`, `tools` |
| Hot-swap support — reload prompt without restarting agent | Agent subscribes to prompt update events |
| `civitas playground` CLI — interactive session with a specified prompt version | Test against live runtime before promoting |
| Dashboard tab — side-by-side prompt diff, test messages, output comparison | Lightweight eval harness backed by EvalLoop (M2.5) |
| A/B traffic splitting between prompt versions | Random split; metrics tracked via OTEL spans |
| SaaS layer — web UI, team collaboration, cross-deployment promotion, analytics | `design/prompt-library.md — to be written` |
| Spec | design/prompt-library.md — to be written |

---

### LLM Gateway

**Status: 💡 Idea — to be specced | Priority: 🔴 High**

A supervised `GenServer` that sits between agents and LLM providers. All agents call `call("llm_gateway", {...})` instead of hitting providers directly. The gateway owns provider routing, fallback chains, cost tracking, rate limiting, and response caching — as supervised stateful processes on the bus.

**What this is not:** a replacement for LiteLLM proxy or Portkey. The implementation will wrap one of those (or expose the same interface) rather than re-implement provider routing for 100+ models.

| Idea | Notes |
|------|-------|
| Provider routing by cost / latency / capability | Route `claude-opus-4-7` to Anthropic, fall back to `gpt-4o` on quota exhaustion |
| Fallback chains | Configurable ordered provider list per model tier |
| Semantic + exact response caching | `CacheStore(GenServer)` child; `civitas[llm-cache]` extra |
| Per-agent cost tracking | Accumulate token spend by agent name; expose via `civitas dashboard` |
| Rate limiting per agent | Prevents a single agent from exhausting provider quota |
| LiteLLM proxy integration | `LiteLLMGateway` subclass as first implementation |
| Spec | design/llm-gateway.md — to be written |

---

### Fabrica — Tools Gateway

**Status: 💡 Idea — to be specced | Priority: 🔴 High**

**Product:** Fabrica (`pip install fabrica`) — lives in `civitas-io/civitas-forge`, not in python-civitas.

Fabrica solves the tool schema token problem: passing all tool schemas to every LLM call is token-expensive and degrades selection accuracy beyond ~20–30 tools. Instead of N schemas, the LLM receives one `find_tools(query)` meta-tool and retrieves only the schema it needs.

Fabrica aggregates tool sources (local ToolStore, MCP servers, Composio, custom), serves a unified namespace, and exposes a retrieval interface. Civitas agents connect to it as a tool source — any other LLM framework can too.

**Dependency chain:** M3.4 (MCP plumbing) → M4.4 (ToolStore) → Fabrica (retrieval)

See RFC 0001 (`docs/rfc/0001-tool-retrieval.md`) for the formal problem statement and proposed interface standard.

| Idea | Notes |
|------|-------|
| `find_tools(query)` meta-tool — one schema sent to LLM, not N | Keyword backend (default) + embedding backend (`fabrica[search]`) |
| Tool source aggregation — local ToolStore, MCP servers, Composio, custom | Pluggable `ToolSource` protocol |
| Unified tool namespace across all sources | `gateway://source/tool_name` address scheme |
| Per-source credential isolation | Each source has its own auth config; agents never see other sources' secrets |
| Tool call sandboxing | Filesystem + network isolation for untrusted tool execution |
| Health monitoring + circuit breaker per source | Unhealthy sources removed from routing automatically |
| MCP-compatible interface | Fabrica itself exposes `list_tools` + `call_tool` — any MCP client can connect |
| Civitas integration — `ToolSource` plugin pointing at Fabrica | `civitas[fabrica]` extra |
| SaaS upgrade path — hosted Fabrica with team tool registry, analytics | Future |
| Spec | `civitas-forge/packages/fabrica/` — to be created |

---

### Skills Gateway

**Status: 💡 Idea — to be specced | Priority: 🟡 Medium**

A supervised registry of composable agent workflows — "skills" — that can be discovered and invoked by name or capability. A skill is a named, versioned sequence of tool calls, LLM steps, or sub-agent invocations exposed as a single callable unit on the bus.

Extends the Capability-Aware Registry (M4.4): where M4.4 answers "which agent can do X?", the Skills Gateway answers "invoke skill X, wherever it runs."

| Idea | Notes |
|------|-------|
| `@skill` decorator — declare a reusable workflow on any agent | Versioned, named, queryable by capability tags |
| Skill discovery by capability / input type | `gateway.find_skill("summarise", input_type="text/html")` |
| Cross-agent skill composition | Skills can invoke other skills; gateway handles routing |
| Skill versioning with semver + forward compatibility | Old callers work when a skill is upgraded |
| Local + remote skill sources | Skills can live in the local registry or a remote Civitas deployment |
| Hosted skills marketplace | Future SaaS layer — shared skills across organisations |
| Spec | design/skills-gateway.md — to be written |
