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
| 4 | [Visual Topology Editor](#m41-visual-topology-editor) | ⏸️ Deferred | — |

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

Agents consume MCP tools and expose themselves as MCP tool servers — no manual wiring.

| Deliverable | Status |
|-------------|--------|
| `self.tools.get("mcp://server/tool")` API on `AgentProcess` | ⏳ |
| Automatic MCP handshake, transport, and schema negotiation | ⏳ |
| Agents expose themselves as MCP tool servers | ⏳ |
| MCP tool calls appear in OTEL traces as tool spans | ⏳ |
| Connection pooling with circuit breakers | ⏳ |

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
