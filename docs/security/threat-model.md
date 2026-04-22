# Threat Model

**Framework:** STRIDE
**Last updated:** April 2026
**Scope:** Civitas runtime v0.3+

---

## Components in scope

| Component | Role |
|-----------|------|
| `AgentProcess` | Core agent unit — runs `handle()`, manages mailbox and state |
| `Supervisor` | Fault tolerance — restart policy, escalation chain |
| `MessageBus` | Name-based routing — delivers messages between agents |
| `InProcessTransport` | In-process asyncio queue transport |
| `ZMQTransport` | Multi-process transport (XSUB/XPUB proxy) |
| `NATSTransport` | Distributed transport (JetStream) |
| `HTTPGateway` | Edge process — translates HTTP to Civitas messages (v0.4+) |
| `StateStore` | Agent state persistence (SQLite, in-memory) |
| `Plugin system` | LLM providers, tools, MCP clients |
| `EvalAgent` | Corrective observability — monitors and corrects agent behaviour |

---

## STRIDE analysis

### AgentProcess

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| Agent code executes arbitrary system calls — supply chain attack via a malicious dependency or compromised agent class | **E** Elevation of Privilege | High | Sandbox agent processes (M4.2); audit third-party agent code before deployment |
| Infinite message loop between agents saturates mailboxes and exhausts CPU | **D** Denial of Service | Medium | Bounded mailboxes (`asyncio.Queue(maxsize=N)`) drop messages at capacity; `EvalAgent` can halt runaway agents |
| `emit_eval()` target name is controlled by calling agent — could redirect eval events to wrong evaluator | **S** Spoofing | Low | Default target is `"eval_agent"`; only override in trusted orchestrator code |
| Agent state in `StateStore` restored on restart — poisoned state persists across crashes | **T** Tampering | Medium | Encrypt SQLite state at rest (M4.2); validate state schema on `on_start()` |
| No built-in audit of which agent sent which message — repudiation possible | **R** Repudiation | Medium | OTEL spans include `sender`, `recipient`, `trace_id` on every message — use OTLP exporter for durable audit trail |

---

### Supervisor

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| Crash-loop attack — compromised child crashes repeatedly to exhaust restart budget and force parent shutdown | **D** Denial of Service | Medium | Sliding-window restart limits (`max_restarts` + `restart_window`); escalation chain terminates the supervisor tree rather than looping forever |
| Restart of a compromised agent re-instantiates malicious code | **E** Elevation of Privilege | High | Immutable agent class references loaded at startup; no dynamic code loading at restart |
| Escalation chain propagates fault upward — a single bad agent can take down the entire tree | **D** Denial of Service | Low | Deliberate design choice (OTP model); scope supervisors narrowly to limit blast radius |

---

### MessageBus

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| Malicious agent sends messages with a spoofed `sender` field | **S** Spoofing | High | `sender` is set by the bus at route time for internal messages; message signing (M4.2) will cryptographically bind `sender` to the sending process |
| `_agency.*` system message namespace accessible to any agent that constructs the right `type` | **S** Spoofing / **E** Elevation of Privilege | High | `_agency.*` validation enforced on all routes in `MessageBus.route()` — only the bus itself may send system messages |
| Glob-pattern `broadcast()` reaches unintended agents | **I** Information Disclosure | Low | Broadcast patterns are caller-controlled; only use from trusted orchestrator agents |
| Message payload contains sensitive data logged at DEBUG level | **I** Information Disclosure | Medium | Disable `logging.DEBUG` in production; configure OTLP exporter to strip `payload` attributes |

---

### Transport layer

#### InProcessTransport

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| Shared asyncio event loop — one agent blocking the loop delays all others | **D** Denial of Service | Medium | Avoid blocking calls in `handle()`; use `asyncio.to_thread()` for CPU-bound work |

#### ZMQTransport

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| Any local process can connect to the XPUB/XSUB proxy and inject messages | **S** Spoofing / **T** Tampering | High | Bind proxy to `127.0.0.1` (not `0.0.0.0`); enable ZMQ CURVE authentication (M4.2) |
| Messages transmitted over IPC/TCP in cleartext (msgpack, not encrypted) | **I** Information Disclosure | High | Enable ZMQ CURVE encryption (M4.2); or terminate TLS at a sidecar (Envoy) |
| No message authentication — MITM can modify in-flight messages | **T** Tampering | High | Message signing (M4.2) |

#### NATSTransport

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| NATS without TLS transmits all messages in cleartext | **I** Information Disclosure | High | Always configure NATS with TLS in production (`tls: {cert, key, ca}` in NATS server config) |
| NATS JetStream subjects are predictable — any authenticated NATS client can subscribe | **I** Information Disclosure | Medium | Use NATS authorization (accounts + users) to isolate Civitas subjects from other workloads |
| No built-in agent identity validation on NATS subject routing | **S** Spoofing | Medium | NATS credential file per Worker process (M4.2); `sender` field validated at application layer |

---

### HTTPGateway (v0.4+)

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| No request authentication by default — any client can send messages to any agent | **S** Spoofing / **E** Elevation of Privilege | High | Deploy API key or JWT middleware on all production routes |
| HTTP request body forwarded as `message.payload` without sanitisation | **T** Tampering | Medium | Validate with `@contract` (Pydantic); agents must not trust `message.payload` without validation |
| Unbounded request rate exhausts agent mailboxes | **D** Denial of Service | High | Add `RateLimiter(GenServer)` middleware; configure `request_timeout` |
| Plaintext HTTP/1.1 exposes request bodies | **I** Information Disclosure | High | Always configure TLS cert/key; HTTP/2 requires TLS (ALPN) |
| Path traversal via unsanitised path parameters | **T** Tampering | Low | `@route` path parameters are string-typed; agents must validate before using as filesystem paths |

---

### StateStore

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| SQLite state file stored in plaintext on disk | **I** Information Disclosure | High | Encrypt at-rest via filesystem encryption or SQLite encryption extension (M4.2); avoid storing secrets in state |
| SQLite file writable by any process with filesystem access | **T** Tampering | High | Restrict file permissions (`chmod 600`); run agents as a dedicated OS user |
| In-memory store is lost on process restart — agent assumes wrong initial state | **T** Tampering | Low | `AgentProcess` restores state from `StateStore` before `on_start()` — in-memory store is intentionally ephemeral |

---

### Plugin system

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| LLM provider API keys in topology YAML committed to source control | **I** Information Disclosure | Critical | Always use `!ENV VAR_NAME` in YAML; never hardcode keys; `gitleaks` pre-commit hook blocks accidental commits |
| Malicious Python package in `additional_dependencies` exfiltrates keys at import time | **S** Spoofing / **I** Information Disclosure | High | Pin all dependency versions; enable Dependabot + pip-audit in CI |
| MCP server connected via `connect_mcp()` executes arbitrary subprocess commands | **E** Elevation of Privilege | High | Only connect MCP servers from trusted sources; validate `command` and `args` at config parse time |
| Tool `execute()` calls are unrestricted — a tool can make arbitrary network calls | **I** Information Disclosure / **E** Elevation of Privilege | Medium | Sandbox tool execution (M4.2); review tool schemas before registration |

---

### EvalAgent

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| EvalAgent itself is compromised — sends false `halt` signals to healthy agents | **D** Denial of Service | Medium | Run `EvalAgent` under its own supervisor subtree; log all correction signals via OTEL |
| Rate limit bypass — attacker sends eval events faster than the window resets | **D** Denial of Service | Low | Rate limiter tracks timestamps server-side; no client-controlled state |
| `civitas.eval.halt` message forged by a non-eval agent | **D** Denial of Service | Medium | Message signing (M4.2) will bind message type to sender identity |

---

## Risk summary

| Risk level | Count | Primary mitigation |
|------------|-------|--------------------|
| Critical | 1 | LLM API keys in YAML — use `!ENV` + gitleaks |
| High | 10 | Message signing, transport TLS/CURVE, gateway auth (M4.2) |
| Medium | 8 | Mailbox bounds, OTEL audit, NATS isolation, state encryption |
| Low | 5 | Broadcast scope, path params, in-memory state |

The majority of High findings are addressed by **M4.2 Security Hardening** (mTLS, message signing, credential isolation, sandboxing).

---

## Out of scope

- Threats to the NATS server itself (covered by NATS documentation)
- Threats to the LLM provider APIs (covered by provider security policies)
- Social engineering or insider threats
- Physical access to the host machine
