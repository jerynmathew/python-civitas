# Documentation Build Plan — python-agency OSS Launch

> Working doc. Updated continuously as items complete.
> Rule: one item at a time, in order. Check off when done.

---

## Status Key

- `[ ]` — not started
- `[~]` — in progress
- `[x]` — complete

---

## Phase 1 — Core Docs (Launch Blockers)

These must exist before the repo goes public.

### 1. `README.md` — Rewrite
`[x]` **Complete rewrite of the front door.**

Current README is a stub. Needs:
- Strong one-liner + positioning ("The BEAM for AI agents, in Python")
- Concrete motivation: what problem it solves and why existing tools fall short
- 15-line supervision example showing crash + auto-recovery (the "aha" moment)
- Feature highlights with brief rationale (not just bullet list)
- Deployment ladder teaser (InProcess → ZMQ → NATS, same code)
- Install + hero demo instructions
- Links to docs, examples, contributing
- Architecture overview diagram (Mermaid)
- Competitor comparison table (Temporal, LangGraph, CrewAI, Akka)

---

### 2. `docs/index.md` — MkDocs Home Page
`[x]` **MkDocs landing page (distinct from README).**

- Shorter than README — entry point for docs site navigation
- "What is Agency?" in 3 sentences
- When to use Agency (and when not to)
- Quick navigation to key sections

---

### 3. `docs/getting-started.md` — Quickstart Guide
`[x]` **Zero-to-running in under 10 minutes.**

Sections:
- Install (`pip install python-agency`)
- Hello Agent (5 lines, no LLM)
- Add supervision — crash + auto-restart walkthrough
- Add an LLM call (`self.llm.chat()`)
- Run with OTEL tracing (console exporter, then Jaeger)
- Next steps

---

### 4. `docs/concepts.md` — Core Concepts
`[x]` **Conceptual foundation — the mental model.**

Covers each primitive with a clear explanation + diagram:
- `AgentProcess` — what it is, lifecycle hooks, mailbox model
- `Supervisor` — strategies explained visually (Mermaid diagrams for ONE_FOR_ONE, ONE_FOR_ALL, REST_FOR_ONE)
- `MessageBus` + `Registry` — how routing works
- `Transport` — the abstraction and why it enables the scaling ladder
- Plugin system — ModelProvider, ToolProvider, StateStore (protocol pattern)
- OTP inspiration — brief framing for those unfamiliar with Erlang

---

### 5. `docs/supervision.md` — Supervision Deep Dive
`[x]` **Everything about fault tolerance.**

- Restart strategies with diagrams (Mermaid)
- Backoff policies (CONSTANT, LINEAR, EXPONENTIAL)
- Sliding window rate limiting (`max_restarts` + `restart_window`)
- Escalation chain — what happens when a supervisor gives up
- Remote agent supervision via heartbeats
- Per-child configuration
- Common patterns: which strategy for which scenario

---

### 6. `docs/messaging.md` — Messaging Patterns
`[x]` **How agents communicate.**

- `send` — fire-and-forget, when to use
- `ask` — request-reply with timeout, ephemeral reply routing explained
- `broadcast` — glob pattern matching
- `reply` — returning from `handle()`
- Message envelope anatomy (fields, trace context)
- Backpressure — bounded mailboxes, what happens when full
- System messages (`_agency.*` prefix — reserved)
- Trace context propagation across agent boundaries

---

### 7. `docs/transports.md` — Transport Layer
`[x]` **The scaling ladder.**

- InProcessTransport — asyncio queues, when to use, limitations
- ZMQTransport — multi-process on one machine, XSUB/XPUB proxy, setup
- NATSTransport — distributed, multi-machine, NATS setup
- Switching transports — same code, topology change only (example)
- Transport protocol — how to write a custom transport
- Mermaid diagram: deployment levels side-by-side

---

### 8. `docs/observability.md` — Observability
`[x]` **Tracing, spans, and metrics.**

- What is automatically traced (messages, LLM calls, tools, supervisor events)
- Span anatomy — `agency.*` attribute namespace
- Console exporter — zero-dependency output format
- OTEL export — `OTEL_EXPORTER_OTLP_ENDPOINT`, Jaeger setup walkthrough
- `llm_span()` and `tool_span()` context managers
- Trace context propagation across processes
- Mermaid diagram: span hierarchy for a multi-agent call chain

---

### 9. `docs/plugins.md` — Plugin System
`[x]` **Extending Agency.**

- ModelProvider — protocol definition, Anthropic usage, LiteLLM usage
- ToolProvider — registering tools with JSON schema, invoking from agent
- StateStore — checkpoint/restore pattern, InMemory vs SQLite
- Installing plugins as extras (`pip install python-agency[anthropic]`)
- Writing a custom plugin — step-by-step for each protocol
- Loading plugins from YAML topology

---

### 10. `docs/topology.md` — YAML Topology Reference
`[x]` **Declarative system definition.**

- Full YAML schema with inline comments
- Supervision block — all fields with types and defaults
- Transport block — per-transport configuration
- Plugins block — model, state, exporters
- Process affinity — assigning agents to workers
- CLI commands: `agency topology validate`, `agency topology show`, `agency topology diff`
- Python DSL ↔ YAML equivalence (side-by-side)

---

### 11. `docs/deployment.md` — Deployment Guide
`[x]` **Level 1 → Level 4 deployment ladder.**

- Level 1: Single process (`InProcessTransport`) — development default
- Level 2: Multi-process (`ZMQTransport`) — single machine scale-up
- Level 3: Distributed (`NATSTransport`) — multi-machine
- Level 4: Containerized (`agency deploy --target docker-compose`)
- Mermaid diagram: each level illustrated
- Environment variables reference
- Production checklist

---

### 12. `docs/faq.md` — FAQ / Comparison Guide
`[x]` **Address the main objections.**

Sections:
- "Why not just use Temporal?"
- "Why not LangGraph with checkpointing?"
- "Why not CrewAI?"
- "Isn't this what Akka does?" (yes — on JVM, BSL-licensed, enterprise-priced)
- "Will the GIL hurt performance?" (I/O-bound reality)
- "Can I use Agency with my existing framework?" (yes — adapters)
- "Agency vs. a plain asyncio task runner — what's the difference?"

---

### 13. `docs/adapters.md` — Framework Adapters
`[x]` **Wrapping existing agents.**

- LangGraphAgent — wrapping a compiled graph, < 10 lines
- OpenAIAgent — wrapping OpenAI SDK agents
- What the adapter gives you (supervision, tracing, transport)
- Limitations — what can't be wrapped cleanly

---

### 14. `docs/architecture.md` — Internals (Contributor Reference)
`[x]` **For contributors and advanced users.**

- Runtime startup sequence (13 steps, Mermaid flow diagram)
- Component wiring — ComponentSet, dependency injection
- Message flow end-to-end (Mermaid sequence diagram)
- Fault handling path — crash → supervisor → restart
- Ephemeral reply routing — how request-reply works under the hood
- Key design decisions with rationale (from Decision Register)

---

### 15. `CONTRIBUTING.md`
`[x]` **How to contribute.**

- Dev setup (`uv` based)
- Running tests
- PR conventions
- Plugin authoring guide
- AGENTS.md maintenance policy (update alongside any public API change)

---

### 16. `CHANGELOG.md`
`[x]` **Initial version history.**

- Reconstruct from milestones: M1.1 → M3.2
- Format: Keep-a-Changelog (https://keepachangelog.com)

---

## Phase 2 — Examples Overhaul

After core docs are complete.

### 17. Examples — Audit & Cleanup
`[x]` **Review all existing examples for quality and correctness.**

- Read each example in `examples/`
- Verify they run cleanly
- Ensure each has a clear docstring/header explaining what it demonstrates
- Remove M-number references (internal milestone IDs — not meaningful to OSS users)

---

### 18. Examples — New: `examples/quickstart/`
`[ ]` **Minimal, polished onboarding examples.**

Four files, each independently runnable, progressively building:
- `01_hello_agent.py` — simplest possible agent (no LLM, no tools)
- `02_supervised_agent.py` — deliberate crash + auto-restart
- `03_multi_agent.py` — three agents forming a pipeline
- `04_with_llm.py` — agent calling Anthropic (or mock)

---

### 19. Examples — New: `examples/patterns/`
`[ ]` **Canonical patterns for common architectures.**

- `fan_out_fan_in.py` — parallel tool calls with aggregation
- `pipeline.py` — sequential agent chain
- `router.py` — dynamic routing based on message content
- `human_in_the_loop.py` — pause for approval, resume on reply

---

### 20. Examples — New: `examples/deployment/`
`[ ]` **Deployment ladder examples.**

- `level1_single_process/` — InProcess, runnable with no deps
- `level2_multi_process/` — ZMQ, with topology YAML
- `level3_distributed/` — NATS, with topology YAML
- `level4_docker/` — generated Docker Compose

---

### 21. `AGENTS.md` — Review & Update
`[ ]` **Verify AGENTS.md is accurate against current codebase.**

- Check all import paths are correct
- Verify Message field names match `messages.py`
- Verify lifecycle hook signatures match `process.py`
- Add any missing common mistakes
- Confirm "do not generate" patterns are exhaustive

---

## Phase 3 — MkDocs Polish

After all content is written.

### 22. `mkdocs.yml` — Complete Nav + Config
`[ ]` **Wire all docs into MkDocs navigation.**

- Add all new pages to `nav:`
- Configure Material theme properly (palette, icons, extensions)
- Enable: `admonitions`, `code annotations`, `mermaid` (via `pymdownx.superfences`)
- Add `mkdocstrings` for API reference generation

---

### 23. API Reference Pages
`[ ]` **Auto-generated API docs via mkdocstrings.**

- `docs/api/runtime.md`
- `docs/api/process.md`
- `docs/api/supervisor.md`
- `docs/api/messages.md`
- `docs/api/transport.md`
- `docs/api/plugins.md`

---

## Progress Tracker

| # | Item | Status |
|---|------|--------|
| 1 | README.md rewrite | `[x]` |
| 2 | docs/index.md | `[x]` |
| 3 | docs/getting-started.md | `[x]` |
| 4 | docs/concepts.md | `[x]` |
| 5 | docs/supervision.md | `[x]` |
| 6 | docs/messaging.md | `[x]` |
| 7 | docs/transports.md | `[x]` |
| 8 | docs/observability.md | `[x]` |
| 9 | docs/plugins.md | `[x]` |
| 10 | docs/topology.md | `[x]` |
| 11 | docs/deployment.md | `[x]` |
| 12 | docs/faq.md | `[x]` |
| 13 | docs/adapters.md | `[x]` |
| 14 | docs/architecture.md | `[x]` |
| 15 | CONTRIBUTING.md | `[x]` |
| 16 | CHANGELOG.md | `[x]` |
| 17 | Examples — audit & cleanup | `[x]` |
| 18 | Examples — quickstart/ | `[ ]` |
| 19 | Examples — patterns/ | `[ ]` |
| 20 | Examples — deployment/ | `[ ]` |
| 21 | AGENTS.md — review & update | `[ ]` |
| 22 | mkdocs.yml — complete nav | `[ ]` |
| 23 | API reference pages | `[ ]` |
