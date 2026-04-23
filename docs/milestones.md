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
| 2 | [Ecosystem — EvalLoop (local)](#m25-evalloop) | ✅ Completed | Apr 2026 |
| 2 | [Ecosystem — Remote Eval Exporters](#m26-remote-eval-exporters) | ✅ Completed | Apr 2026 |
| 3 | [Developer Experience — CLI & Dashboard](#phase-3-developer-experience) | ✅ Completed | Mar 2026 |
| 3 | [Developer Experience — MCP Integration](#m34-mcp-integration) | ✅ Completed | Apr 2026 |
| 3 | [Developer Experience — GenServer](#m35-genserver) | ✅ Completed | Apr 2026 |
| — | [Infrastructure & Release](#infrastructure--release) | ✅ Completed | Apr 2026 |
| 4 | [Dynamic Agent Spawning](#m41b-dynamic-agent-spawning) | ⏳ Planned | v0.4 |
| 4 | [Security Hardening](#m42-security-hardening) | ⏳ Planned | v0.4 |
| 4 | [Codebase Security & Enterprise Posture](#m43-codebase-security--enterprise-posture) | ✅ Completed | Apr 2026 |
| 4 | [Capability-Aware Registry](#m44-capability-aware-registry) | ⏳ Planned | v0.5 |
| 4 | [HTTP Gateway](#http-gateway) | ✅ Completed | Apr 2026 |
| 4 | [Gateway API Surface](#gateway-api-surface) | ✅ Completed | Apr 2026 |
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

### M2.5 — EvalLoop (Local)

**Status: ✅ Completed — April 2026**

Corrective observability loop: a supervised `EvalAgent` process monitors agent behaviour and injects correction signals back into running agents. Local in-process evaluation only — remote eval engine integrations are M2.6. See [design spec](design/evalloop.md).

| Deliverable | Status |
|-------------|--------|
| `civitas/evalloop.py` — `EvalEvent`, `CorrectionSignal`, `EvalAgent` base class | ✅ |
| `AgentProcess.emit_eval(event_type, payload, eval_agent)` — emit observable events | ✅ |
| `AgentProcess.on_correction(message)` — override hook for nudge/redirect signals | ✅ |
| `civitas.eval.halt` message type — cleanly stops target agent (on_stop still runs) | ✅ |
| Rate limiting — sliding window per target agent (`max_corrections_per_window`, `window_seconds`) | ✅ |
| `EvalExporter` protocol — interface defined, not implemented (M2.6) | ✅ |
| Topology YAML — `type: eval_agent` shorthand in `Runtime.from_config()` | ✅ |
| 20 unit + integration tests | ✅ |
| `EvalAgent` exported from `civitas` top-level package | ✅ |

#### Implementation checklist

1. **Core module — `civitas/evalloop.py`**
   - [x] `EvalEvent` dataclass: `agent_name`, `event_type`, `payload`, `trace_id`, `message_id`, `timestamp`
   - [x] `CorrectionSignal` dataclass: `severity` (nudge / redirect / halt), `reason`, `payload`
   - [x] `EvalExporter` protocol: `async export(event: EvalEvent) -> None`
   - [x] `EvalAgent(AgentProcess)` — `handle()` routes `civitas.eval.event` messages
   - [x] `on_eval_event(event: EvalEvent) -> CorrectionSignal | None` — override point
   - [x] Rate limiter — sliding window, keyed by target agent name, drops + logs when exceeded
   - [x] For nudge/redirect: send `civitas.eval.correction` to target agent
   - [x] For halt: send `civitas.eval.halt` to target agent

2. **AgentProcess integration**
   - [x] `emit_eval(event_type, payload, eval_agent="eval_agent")` — sends `civitas.eval.event`; no-op if bus not wired
   - [x] `on_correction(message: Message)` — override hook called on `civitas.eval.correction`
   - [x] `civitas.eval.halt` handled in `_message_loop()` — breaks loop, on_stop() still runs

3. **Runtime + package**
   - [x] `type: eval_agent` shorthand in `Runtime.from_config()` `_build_node()`
   - [x] `EvalAgent` exported from `civitas.__init__`

4. **Tests (≥ 12 unit + ≥ 1 integration)**
   - [x] `EvalEvent` and `CorrectionSignal` field validation
   - [x] `on_eval_event()` returning None sends no correction
   - [x] nudge signal delivered to `on_correction()` hook
   - [x] redirect signal delivered to `on_correction()` hook
   - [x] halt signal stops target agent (status → STOPPED, on_stop runs)
   - [x] Rate limiter allows corrections up to the window limit
   - [x] Rate limiter drops corrections beyond the window limit
   - [x] Rate limiter resets after window_seconds
   - [x] `emit_eval()` is no-op when bus not wired
   - [x] `emit_eval()` reaches EvalAgent in a live runtime
   - [x] Integration: full supervision tree — EvalAgent halts a misbehaving sibling

5. **Example + release**
   - [x] `examples/eval_agent.py` — policy enforcement with halt, redirect, nudge
   - [x] `CHANGELOG.md` entry

---

### M2.6 — Remote Eval Exporters

**Status: ✅ Completed — v0.4 | Priority: 🔴 High**

Plugin adapters connecting Civitas's `EvalEvent` stream to external eval engines. All platforms consume the same `EvalEvent` schema; each exporter translates to the platform's expected format. OTEL GenAI Semantic Conventions are the alignment layer — `EvalEvent` fields map directly to standard OTEL attributes. See [design spec](design/evalloop.md).

| Deliverable | Status |
|-------------|--------|
| `EvalExporter` protocol implementation + registration on `EvalAgent` | ✅ |
| `civitas[arize]` — Arize Phoenix exporter (OTEL GenAI spans via OTLP) | ✅ |
| `civitas[fiddler]` — Fiddler exporter (export to Fiddler AI; two-way guardrail receive deferred to M4.2) | ✅ |
| `civitas[langfuse]` — Langfuse exporter (open-source, self-hostable) | ✅ |
| `civitas[braintrust]` — Braintrust exporter | ✅ |
| `civitas[langsmith]` — LangSmith exporter | ✅ |
| `emit_eval()` forwards to all registered exporters in addition to local EvalAgent | ✅ |
| Topology YAML — declare exporters per eval_agent node | ✅ |
| ≥ 5 unit tests per exporter (mocked SDK calls) | ✅ |

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

**Status: ✅ Completed — April 2026**

MCP protocol plumbing — the wire layer between Civitas agents and MCP tool servers. Agents call tools by direct address (`mcp://server/tool`); the runtime handles handshake, transport, schema negotiation, and tracing. Agents also expose themselves as MCP servers so external LLM clients can discover and call them.

**Scope:** protocol wire layer only. Connection pooling, circuit breakers, unified tool namespacing, and semantic retrieval are **not** in scope — they belong to Fabrica. See [design spec](design/mcp-integration.md).

**Dependency chain:** M3.4 → M4.4 (ToolStore) → Fabrica (pooling + retrieval)

| Deliverable | Status |
|-------------|--------|
| `civitas[mcp]` optional extra — `mcp>=1.0` dependency | ✅ |
| `MCPClient` — connect (stdio + SSE), `list_tools`, `call_tool`, persistent session via `AsyncExitStack` | ✅ |
| `MCPTool(ToolProvider)` — `mcp://server_name/tool_name` name scheme | ✅ |
| `AgentProcess.connect_mcp()` — connect + auto-register tools into `self.tools`; idempotent | ✅ |
| `self.tools.get("mcp://server/tool")` resolves to the registered `MCPTool` | ✅ |
| `MCPTool.execute()` emits `civitas.mcp.call` OTEL span | ✅ |
| `CivitasMCPServer(GenServer)` — deferred to Fabrica (scope boundary decision) | ⏸️ |
| Topology YAML `mcp.servers` block — auto-connect at agent startup | ✅ |
| 23 unit tests | ✅ |

**Explicitly out of scope for M3.4:**
- Connection pooling / persistent sessions — Fabrica (`MCPToolSource`)
- Circuit breakers per server — Fabrica
- Semantic or keyword tool retrieval (`find_tools`) — Fabrica
- Unified cross-agent tool namespace — M4.4 ToolStore
- Per-agent credential isolation — M4.2 Security Hardening

#### Implementation checklist

Ordered tasks — each step is independently mergeable.

1. **Package setup**
   - [ ] `civitas/mcp/__init__.py` — package stub
   - [ ] `civitas/mcp/types.py` — `MCPServerConfig` (name, transport, command/args/env/url), `MCPToolSchema`
   - [ ] `civitas[mcp]` extra in `pyproject.toml` — `mcp>=1.0`

2. **MCP client**
   - [ ] `civitas/mcp/client.py` — `MCPClient.__init__(config: MCPServerConfig)`
   - [ ] `MCPClient.list_tools()` — stdio transport: open subprocess session, call `list_tools`, close
   - [ ] `MCPClient.list_tools()` — SSE transport: open HTTP session, call `list_tools`, close
   - [ ] `MCPClient.call_tool(name, arguments)` — stdio transport
   - [ ] `MCPClient.call_tool(name, arguments)` — SSE transport

3. **MCPTool**
   - [ ] `civitas/mcp/tool.py` — `MCPTool(ToolProvider)` wrapping `MCPClient` + `MCPToolSchema`
   - [ ] `MCPTool.name` returns `mcp://server_name/tool_name`
   - [ ] `MCPTool.schema` returns the JSON Schema from the MCP tool definition
   - [ ] `MCPTool.execute(**kwargs)` calls `client.call_tool()` and returns result
   - [ ] `MCPTool.execute()` emits `civitas.mcp.call` OTEL span (attributes: server, tool, transport)

4. **AgentProcess integration**
   - [ ] `AgentProcess.connect_mcp(config)` — creates `MCPClient`, calls `list_tools`, registers each as `MCPTool` in `self.tools`
   - [ ] `connect_mcp()` is idempotent: deregisters existing tools for the same server before re-registering
   - [ ] `self.tools.get("mcp://github/create_issue")` resolves correctly via registered name

5. **MCP server exposure**
   - [ ] `civitas/mcp/server.py` — `CivitasMCPServer(GenServer)`
   - [ ] `CivitasMCPServer.init()` — starts MCP stdio server in background task via `mcp.Server`
   - [ ] `list_tools` handler — returns schemas from injected `ToolRegistry`
   - [ ] `call_tool` handler — calls the matching `MCPTool.execute()` or raises `ToolNotFoundError`

6. **Topology YAML support**
   - [ ] Runtime loader reads `mcp.servers` block, creates `MCPServerConfig` instances
   - [ ] Agents auto-connect configured servers during startup (before first message)
   - [ ] `mcp.expose.enabled: true` starts `CivitasMCPServer` as a supervised child
   - [ ] `civitas topology validate` accepts `mcp:` section without errors

7. **Tests (≥ 10 unit, ≥ 2 integration)**
   - [ ] `MCPServerConfig` validation (missing transport fields, unknown transport)
   - [ ] `MCPTool.name` follows `mcp://` scheme
   - [ ] `MCPTool.schema` returns correct JSON Schema
   - [ ] `MCPTool.execute()` calls `client.call_tool()` with correct args
   - [ ] `MCPTool.execute()` emits OTEL span
   - [ ] `connect_mcp()` registers tools in `self.tools`
   - [ ] `connect_mcp()` deregisters old tools on reconnect (idempotency)
   - [ ] `self.tools.get("mcp://server/tool")` returns correct tool
   - [ ] `CivitasMCPServer` `list_tools` returns all registered tools
   - [ ] `CivitasMCPServer` `call_tool` routes to correct tool
   - [ ] Integration: agent connects to real stdio MCP echo server, calls a tool
   - [ ] Integration: `CivitasMCPServer` handles `list_tools` request from real MCP client

8. **Release**
   - [ ] `CHANGELOG.md` entry under `## [0.3.0]`
   - [ ] Example: `examples/mcp_agent.py` — agent connecting to a stdio MCP server
   - [ ] `mkdocs.yml` nav updated with MCP integration design doc

---

### M3.5 — GenServer

**Status: ✅ Completed — April 2026**

OTP-style generic server primitive for separating stateful API/RPC service processes from AI agent processes on the message bus. See [design spec](design/genserver.md).

| Deliverable | Status |
|-------------|--------|
| `GenServer` base class with `handle_call` / `handle_cast` / `handle_info` dispatch | ✅ |
| `call()` — synchronous request-reply with timeout | ✅ |
| `cast()` — async fire-and-forget | ✅ |
| `send_after()` — delayed self-message (tick / timer support) | ✅ |
| `init()` — startup initialisation hook | ✅ |
| Supervision-compatible (works as a child of any `Supervisor`) | ✅ |
| Topology YAML support (`type: gen_server`) | ✅ |
| 19 unit tests | ✅ |
| `examples/rate_limiter.py` — token-bucket rate limiter demo | ✅ |

#### Implementation checklist

Ordered tasks — each step is independently mergeable.

1. **Core module — `civitas/genserver.py`**
    - [ ] `GenServer(AgentProcess)` class — no LLM or tool plugin injection
    - [ ] `handle()` dispatcher: route by `reply_to` → `handle_call`; `__cast__` marker → `handle_cast`; else → `handle_info`
    - [ ] `handle_call` / `handle_cast` / `handle_info` stubs with correct signatures
    - [ ] `async def init()` hook invoked once at process start
    - [ ] `send_after(delay_ms, payload)` — schedules `handle_info` to self
    - [ ] Track `send_after` tasks; cancel all on `stop()`
    - [ ] Enforce `handle_call` returns a dict (reject `None` to prevent caller hangs)
2. **`call()` / `cast()` aliases**
    - [ ] `AgentProcess.call(name, payload, timeout)` — alias over existing `ask()`
    - [ ] `AgentProcess.cast(name, payload)` — `send()` with `__cast__` marker
    - [ ] `Runtime.call()` / `Runtime.cast()` — external entry points
3. **Topology YAML support**
    - [ ] Loader accepts `type: gen_server` (module/class resolution identical to `type: agent`)
    - [ ] `civitas topology validate` passes for gen_server nodes
    - [ ] `civitas topology show` renders gen_server with distinct icon/label
    - [ ] `civitas topology diff` treats gen_server nodes correctly
4. **Observability**
    - [ ] Emit `civitas.genserver.call` span for `handle_call`
    - [ ] Emit `civitas.genserver.cast` span for `handle_cast`
    - [ ] Emit `civitas.genserver.info` span for `handle_info`
    - [ ] Trace propagation preserved across `call()` boundaries
5. **Tests (≥ 15 cases in `tests/test_genserver.py`)**
    - [ ] `handle_call` returns reply via `reply_to`
    - [ ] `handle_cast` runs, no reply emitted
    - [ ] `handle_info` invoked for non-call non-cast messages
    - [ ] `call()` timeout raises within configured bound
    - [ ] `send_after` fires `handle_info` after delay
    - [ ] `send_after` tasks cancelled cleanly on `stop()`
    - [ ] `init()` runs before first message handled
    - [ ] GenServer as child of `ONE_FOR_ONE`, `ONE_FOR_ALL`, `REST_FOR_ONE` supervisors
    - [ ] Restart triggers `init()` again (state resets unless `StateStore` configured)
    - [ ] `StateStore`-backed state survives restart
    - [ ] `self.llm` not present on GenServer instance
    - [ ] `self.tools` not present on GenServer instance
    - [ ] `handle_call` returning non-dict raises
    - [ ] GenServer ↔ AgentProcess sibling communication round-trip
    - [ ] Topology YAML round-trip: load → run → `topology show` matches
6. **Example + documentation**
    - [ ] `examples/rate_limiter/` — end-to-end `RateLimiter(GenServer)` with consumer agent
    - [ ] User guide page referencing `docs/design/genserver.md`
    - [ ] API reference entry for `civitas.genserver`
    - [ ] `mkdocs.yml` nav updated
7. **Release**
    - [ ] `CHANGELOG.md` entry under `## [0.3.0]`
    - [ ] Cross-reference M3.4 (MCP) and M2.5 (EvalLoop) for coordinated v0.3 cut

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

### M4.3 — Codebase Security & Enterprise Posture

**Status: ✅ Completed — April 2026 | Priority: 🔴 High**

Complements M4.2. Where M4.2 hardens the **runtime** (mTLS, message signing, credential isolation, sandboxing), M4.3 hardens the **codebase and supply chain** so enterprises have a clear security story before adoption: known vulnerabilities tracked, dependencies scanned, secrets never committed, a published threat model, and a documented disclosure process.

The deliverables are split across tooling (CI-enforced scanners), documentation (threat model, security architecture, adoption checklist), and process (disclosure policy, release notes, third-party audit).

| Deliverable | Status |
|-------------|--------|
| SAST in CI — Bandit + Semgrep on every PR, fail build on `HIGH`+ | ✅ |
| Dependency scanning — `pip-audit` in CI + Dependabot weekly | ✅ |
| SBOM generation — CycloneDX SBOM published with every release | ✅ |
| Secret scanning — `gitleaks` pre-commit hook + CI job on full history | ✅ |
| `docs/security/threat-model.md` — STRIDE analysis per runtime component | ✅ |
| `docs/security/architecture.md` — security model (trust boundaries, supervision, transport isolation) | ✅ |
| `SECURITY.md` — responsible disclosure policy, contact, supported versions, response SLAs | ✅ |
| `docs/security/enterprise-checklist.md` — adoption checklist (deployment hardening, config review, audit log integration) | ✅ |
| External security audit before v1.0 — fix all `HIGH`+ findings, publish summary | ⏳ Deferred to pre-v1.0 |
| Continuous posture — CVE watch on runtime deps, security release notes, CVSS-scored advisories | ⏳ Ongoing process |

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

**Status: ✅ Completed — April 2026**

Supervised edge process bridging external HTTP traffic into the Civitas message bus. HTTP/1.1 + HTTP/2 (uvicorn) and HTTP/3 / QUIC (aioquic) in v0.4. gRPC deferred to v0.5. See [design spec](design/http-gateway.md).

| Deliverable | Status |
|-------------|--------|
| `HTTPGateway(AgentProcess)` — ASGI app, request translation, route table | ⏳ |
| HTTP/1.1 + HTTP/2 via uvicorn[standard] — uvloop + httptools (`civitas[http]`) | ⏳ |
| HTTP/3 / QUIC via aioquic — `Alt-Svc` header, 0-RTT (`civitas[http3]`) | ⏳ |
| TLS config from topology YAML / env vars | ⏳ |
| Topology YAML support (`type: http_gateway`) | ⏳ |
| Graceful drain on supervisor shutdown | ⏳ |
| ≥ 20 unit tests + ≥ 5 integration tests | ⏳ |
| `examples/http_gateway.py` | ⏳ |
| gRPC via grpclib / grpcio | ⏸️ v0.5 |
| Custom `.proto` loading from `proto_dir` | ⏸️ v0.5 |

#### Implementation checklist

1. **Package setup**
   - [ ] `civitas/gateway/__init__.py` — package stub, re-export `HTTPGateway`
   - [ ] `civitas[http]` extra in `pyproject.toml` — `uvicorn[standard]>=0.30`
   - [ ] `civitas[http3]` extra — `aioquic>=1.0`

2. **Core — `civitas/gateway/core.py`**
   - [ ] `GatewayConfig` dataclass — `host`, `port`, `port_quic`, `tls_cert`, `tls_key`, `request_timeout`, `enable_http3`
   - [ ] `HTTPGateway(AgentProcess)` — holds config, route table, uvicorn server reference
   - [ ] `on_start()` — install uvloop (Linux/macOS), start uvicorn server as background task
   - [ ] `on_stop()` — signal uvicorn to drain in-flight requests, cancel server task
   - [ ] `handle()` — handles internal messages (e.g., topology-triggered reconfiguration); no-op for now

3. **ASGI app — `civitas/gateway/asgi.py`**
   - [ ] `GatewayASGI.__call__(scope, receive, send)` — ASGI callable
   - [ ] HTTP scope: parse method, path, headers, body
   - [ ] Route lookup: path + method → agent name, mode (`call` vs `cast`)
   - [ ] Default routes: `POST /agents/{name}` → `call`, `POST /agents/{name}/cast` → `cast`
   - [ ] HTTP → `Message` translation: body → `payload`, `X-Civitas-Type` → `type`, `traceparent` → trace context
   - [ ] `call()` mode: await reply, serialise `payload` as JSON response body
   - [ ] `cast()` mode: fire-and-forget, return HTTP 202
   - [ ] Timeout: `asyncio.wait_for` with `request_timeout`; return HTTP 504 on expiry
   - [ ] Error mapping: `payload.error` → 400, no route → 404, unhandled exception → 500

4. **Router — `civitas/gateway/router.py`**
   - [ ] `RouteEntry` dataclass — `method`, `path_pattern`, `agent`, `mode`
   - [ ] `RouteTable` — ordered list of `RouteEntry`; `match(method, path)` returns `(RouteEntry, path_params)`
   - [ ] Path parameter extraction: `{name}` segments captured into dict
   - [ ] Default route fallback when no custom routes are configured
   - [ ] YAML route loading: `config.routes` list → `RouteEntry` instances

5. **HTTP/3 — `civitas/gateway/h3.py`**
   - [ ] `H3Server` — wraps aioquic QUIC server; runs on `port_quic` (UDP)
   - [ ] HTTP/3 request → same `GatewayASGI` handler (reuse ASGI layer)
   - [ ] `Alt-Svc: h3=":port_quic"` header injected into all HTTP/1.1 and HTTP/2 responses
   - [ ] `H3Server` started / stopped alongside uvicorn in `on_start()` / `on_stop()`

6. **Topology YAML support**
   - [ ] `type: http_gateway` in `Runtime.from_config()` `_build_node()`
   - [ ] `GatewayConfig` populated from YAML `config:` block; `!ENV` resolver for TLS cert/key paths
   - [ ] `civitas topology validate` accepts `type: http_gateway` nodes without errors
   - [ ] `civitas topology show` displays gateway node with `[http]` / `[http3]` label

7. **Tests (≥ 20 unit, ≥ 5 integration)**
   - [ ] `RouteTable.match()` — exact path, path parameters, method mismatch, no route
   - [ ] Default route fallback: `POST /agents/foo` → `call("foo", body)`
   - [ ] `call` mode: reply payload returned as JSON 200
   - [ ] `cast` mode: 202 returned immediately
   - [ ] Timeout: `request_timeout=0.001` → 504
   - [ ] Error mapping: `payload.error` → 400; unhandled exception → 500
   - [ ] No route: 404
   - [ ] `traceparent` header propagated into `message.trace_id`
   - [ ] `GatewayConfig` validation: missing TLS cert when `enable_http3=True`
   - [ ] `on_start()` installs uvloop on Linux
   - [ ] `on_stop()` cancels server task cleanly
   - [ ] Integration: real HTTP client (`httpx.AsyncClient`) → gateway → `AgentProcess` → reply
   - [ ] Integration: concurrent requests all return correct replies
   - [ ] Integration: gateway node in topology YAML starts correctly via `Runtime.from_config()`

8. **Example + release**
   - [ ] `examples/http_gateway.py` — minimal REST API with two agent endpoints
   - [ ] `CHANGELOG.md` entry under `## [Unreleased]`

---

### Gateway API Surface

**Status: ✅ Completed — April 2026**

Declarative routes, Pydantic request/response validation, middleware chain, and auto-generated OpenAPI 3.1 docs on top of `HTTPGateway`. See [design spec](design/gateway-api-surface.md).

| Deliverable | Status |
|-------------|--------|
| `@route` decorator — documents HTTP method + path on agent handler (YAML is authoritative for wiring) | ⏳ |
| Path parameter extraction into `message.payload` | ⏳ |
| `@contract` decorator — Pydantic request/response validation, 422 error shape | ⏳ |
| `GatewayRequest` / `GatewayResponse` / `NextMiddleware` types | ⏳ |
| Global + route-scoped middleware chain | ⏳ |
| Stateful GenServer middleware via `request.gateway.call()` | ⏳ |
| Auto-generated OpenAPI 3.1 spec at `GET /openapi.json` | ⏳ |
| Swagger UI at `GET /docs`, ReDoc at `GET /redoc` | ⏳ |
| YAML-declared routes and schemas (no decorators required) | ⏳ |
| `civitas topology validate` cross-checks YAML routes against `@route` decorators | ⏳ |
| ≥ 15 unit tests + ≥ 3 integration tests | ⏳ |

**Routing authority:** YAML is the single source of truth for gateway wiring. `@route` stores metadata on the method object only — it is never read by the gateway at runtime. Its value is (1) colocated documentation of intent and (2) a machine-checkable annotation that `civitas topology validate` cross-references against YAML to warn on drift.

#### Implementation checklist

1. **Types — `civitas/gateway/types.py`**
   - [ ] `GatewayRequest` dataclass — `method`, `path`, `path_params`, `query_params`, `headers`, `body`, `client_ip`, `gateway` (AgentProcess ref)
   - [ ] `GatewayResponse` dataclass — `status`, `body`, `headers`
   - [ ] `NextMiddleware` type alias — `Callable[[GatewayRequest], Awaitable[GatewayResponse]]`

2. **Route decorator — `civitas/gateway/routing.py`**
   - [ ] `@route(method, path, mode="call")` — stores `_civitas_route` metadata dict on the decorated function; no side effects, no global registry
   - [ ] `RouteTable.from_yaml(routes_config)` — sole runtime source; builds `RouteEntry` list from topology YAML `routes:` block
   - [ ] `RouteTable.from_class(cls)` — validation-only helper; scans class methods for `_civitas_route` metadata; used exclusively by `civitas topology validate`
   - [ ] `civitas topology validate`: when a gateway node references an agent, import the class and warn if a YAML route has no matching `@route` on the handler, or if a `@route` exists with no corresponding YAML entry

3. **Contract decorator — `civitas/gateway/contracts.py`**
   - [ ] `@contract(request=Model, response=Model)` — stores `_civitas_contract` metadata on the function; `request` and `response` are optional Pydantic `BaseModel` subclasses
   - [ ] Request validation in ASGI dispatch: if route has a contract, `Model.model_validate(body)` before calling the bus; 422 on `ValidationError` with FastAPI-compatible error shape `{"detail": [...]}`
   - [ ] Response validation: `Model.model_validate(reply_payload)` after reply received; 500 on mismatch
   - [ ] No-op when `@contract` not applied — pass-through

4. **Middleware — `civitas/gateway/middleware.py`**
   - [ ] `MiddlewareChain` — ordered list of async callables; builds `call_next` chain via closure
   - [ ] Global middleware loaded from `config.middleware` (dotted import path → callable)
   - [ ] Route-scoped middleware loaded from `route.middleware`
   - [ ] Execution order: global → route-scoped → contract validation → bus dispatch
   - [ ] Short-circuit: middleware returning `GatewayResponse` without calling `call_next` skips remainder

5. **Wire into ASGI — `civitas/gateway/asgi.py` updates**
   - [ ] Replace direct bus dispatch with: build `GatewayRequest` → run middleware chain → contract validate → dispatch
   - [ ] `GatewayRequest.gateway` set to the `HTTPGateway` instance (for stateful GenServer middleware)
   - [ ] Contract metadata read from the agent class method via `@route` + `@contract` on the matched handler

6. **OpenAPI — `civitas/gateway/openapi.py`**
   - [ ] `OpenAPIBuilder` — reads `RouteTable` (from YAML) + loads agent class to read `@contract` metadata
   - [ ] Generates OpenAPI 3.1 `paths` from route entries
   - [ ] Request body schema from `@contract(request=Model)` via `Model.model_json_schema()`
   - [ ] Response schema from `@contract(response=Model)`
   - [ ] Operation summary from first line of matched handler's docstring
   - [ ] Operation description from full docstring
   - [ ] Tags from agent name
   - [ ] Auto-includes 422 response schema when request model is declared
   - [ ] `GET /openapi.json` — returns generated spec
   - [ ] `GET /docs` — Swagger UI (CDN-hosted, no static assets)
   - [ ] `GET /redoc` — ReDoc UI (CDN-hosted)
   - [ ] `docs.enabled: false` config disables all three endpoints

7. **Tests (≥ 15 unit, ≥ 3 integration)**
   - [ ] `@route` stores metadata on the function, no global registry side-effect
   - [ ] `RouteTable.from_yaml()` builds routes correctly from config dict
   - [ ] `RouteTable.from_class()` reads `@route` metadata from class methods
   - [ ] `topology validate` warns when YAML route has no matching `@route` on agent
   - [ ] `topology validate` warns when `@route` exists with no YAML entry
   - [ ] Path parameters extracted correctly from URL
   - [ ] `@contract` request validation: valid body → dispatched; invalid → 422 with FastAPI error shape
   - [ ] `@contract` response validation: valid reply → 200; invalid → 500
   - [ ] Middleware chain: all middleware called in order
   - [ ] Middleware short-circuit: returning response without `call_next` skips rest of chain
   - [ ] Global middleware runs before route-scoped middleware
   - [ ] `request.gateway.call()` reaches a sibling GenServer
   - [ ] `/openapi.json` returns valid OpenAPI 3.1 spec
   - [ ] `/docs` returns 200 with Swagger UI HTML
   - [ ] `docs.enabled: false` → `/docs` returns 404
   - [ ] Tags populated from agent name
   - [ ] Integration: `@route` + `@contract` end-to-end with real HTTP client

8. **Example + release**
   - [ ] `examples/gateway_api.py` — full example: `@route`, `@contract`, middleware, `/docs`
   - [ ] `CHANGELOG.md` entry

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
