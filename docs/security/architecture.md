# Security Architecture

**Last updated:** April 2026
**Scope:** Civitas runtime v0.3+

This document describes the security model of the Civitas runtime: trust boundaries, the supervision security model, transport isolation, credential handling, and the roadmap toward full hardening.

---

## Trust boundaries

Civitas has three trust zones:

```
┌─────────────────────────────────────────────────────────────────┐
│  Zone 1 — Runtime process (highest trust)                       │
│                                                                 │
│  Supervisor tree  ·  MessageBus  ·  InProcessTransport         │
│  EvalAgent        ·  StateStore  ·  Plugin loader               │
│                                                                 │
│  All objects share the same OS process and event loop.          │
│  Trust is implicit — no authentication between components.      │
└──────────────────────────────┬──────────────────────────────────┘
                               │  ZMQTransport / NATSTransport
┌──────────────────────────────▼──────────────────────────────────┐
│  Zone 2 — Worker processes (same machine, different PID)        │
│                                                                 │
│  Worker  ·  Remote agents  ·  ZMQ IPC or TCP socket            │
│                                                                 │
│  Workers connect to the Runtime's broker. Messages cross OS     │
│  process boundaries. Without M4.2, there is no authentication   │
│  or encryption on this boundary.                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │  NATSTransport (TCP + TLS)
┌──────────────────────────────▼──────────────────────────────────┐
│  Zone 3 — Remote machines (distributed deployment)              │
│                                                                 │
│  Workers on separate hosts  ·  NATS server cluster             │
│                                                                 │
│  Traffic crosses network. TLS must be configured on the NATS    │
│  server. Civitas sends credentials via NATS credential file.    │
└─────────────────────────────────────────────────────────────────┘
                               │  HTTP/HTTPS
┌──────────────────────────────▼──────────────────────────────────┐
│  Zone 4 — External clients (untrusted)                          │
│                                                                 │
│  HTTP/gRPC clients  ·  MCP clients  ·  Browser / mobile apps   │
│                                                                 │
│  All Zone 4 traffic enters through HTTPGateway (v0.4+).        │
│  Must be authenticated at the gateway boundary before reaching  │
│  the message bus. Agents never handle raw HTTP.                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Supervision security model

The Supervisor is a fault-tolerance mechanism, not a security boundary. Key properties:

**Blast radius control**

- Each `Supervisor` node contains failures to its subtree.
- A child that exhausts its restart budget causes the supervisor to escalate to its parent — not a system-wide crash.
- To limit blast radius, scope supervisors narrowly: one supervisor per functional group of agents, not one supervisor for everything.

**Restart identity**

- Agents restart with the same class, name, and configuration loaded at startup.
- There is no dynamic code loading at restart — the agent class is the same Python object reference bound at `Runtime.start()`.
- State is restored from `StateStore` before `on_start()` runs. If state is corrupted, `on_start()` should validate and reset it.

**EvalAgent as a security layer**

- `EvalAgent` is a supervised process that can halt misbehaving agents.
- It is itself supervised — if it crashes, the supervisor restarts it. Use `ONE_FOR_ONE` strategy so an `EvalAgent` crash does not restart the agents it monitors.
- Rate limiting (sliding window per target) prevents `EvalAgent` from being used as a DoS tool.

---

## Transport isolation

### InProcessTransport (Level 1)

All agents share one OS process. The only isolation is Python's asyncio event loop — there is no OS-level process isolation.

**Implication:** A compromised agent can read Python objects in the same process. Trust all agents in a single-process deployment equally.

**Mitigation (v0.4+):** Run untrusted agents in separate Worker processes using ZMQ or NATS transport.

---

### ZMQTransport (Level 2 — single machine, multiple processes)

The ZMQ proxy binds on `127.0.0.1` by default — only local processes can connect.

**Current posture (v0.3):**

- No authentication: any local process that knows the port can connect and inject messages.
- No encryption: messages are msgpack-encoded, not encrypted.
- `sender` field in `Message` is set by the sending agent — not verified by the bus.

**Planned hardening (M4.2):**

- ZMQ CURVE authentication: each Worker generates a keypair; the Runtime validates Worker public keys against a known-keys file.
- ZMQ CURVE encryption: all messages between Runtime and Workers are encrypted at the ZMQ layer.
- Message signing: `Message` includes an HMAC over the payload; the bus verifies on receipt.

---

### NATSTransport (Level 3 — multi-machine)

NATS provides subject-based pub/sub with optional TLS and authentication.

**Current posture (v0.3):**

- TLS is optional and must be configured on the NATS server (not by Civitas).
- Each Worker uses a NATS credential file to authenticate with the NATS server.
- Subject names follow the pattern `civitas.<name>` — any authenticated NATS client on the same server can publish/subscribe.

**Required production configuration:**

```yaml
# topology.yaml
transport:
  type: nats
  url: "nats://nats.internal:4222"
  credentials: "/run/secrets/nats.creds"   # NATS credential file (NKey or JWT)
```

**Recommended NATS server configuration:**

- Enable TLS with a trusted CA.
- Use [NATS accounts](https://docs.nats.io/running-a-nats-service/configuration/securing_nats/accounts) to isolate Civitas subjects from other applications on the same NATS server.
- Restrict subject publish/subscribe permissions per account.

**Planned hardening (M4.2):**

- Per-Worker NATS credential files with scoped subject permissions.
- Message signing layer on top of NATS (same HMAC scheme as ZMQ).

---

## Credential handling

### API keys (LLM providers)

**Rule:** Never hardcode API keys in topology YAML or agent code.

Use the `!ENV` YAML tag to reference environment variables at parse time:

```yaml
plugins:
  llm:
    type: anthropic
    api_key: !ENV ANTHROPIC_API_KEY
```

The `!ENV` resolver raises `PluginError` at startup if the variable is missing — fast-fail rather than silently proceeding with no credentials.

**Runtime secret injection options:**

- Kubernetes Secrets mounted as environment variables
- Docker Swarm secrets mounted at `/run/secrets/` and read via env
- HashiCorp Vault agent sidecar injecting credentials as env vars

Civitas does not implement a secrets management system — it delegates to the deployment layer.

### MCP server credentials

MCP server configs may include `env` fields for passing credentials to stdio subprocesses:

```yaml
mcp:
  servers:
    - name: github
      transport: stdio
      command: npx
      args: [-y, "@modelcontextprotocol/server-github"]
      env:
        GITHUB_PERSONAL_ACCESS_TOKEN: !ENV GITHUB_TOKEN
```

These env vars are passed to the subprocess directly — they are not stored in Civitas state.

### Secrets in agent state

`StateStore` persists `self.state` across restarts. Do not store secrets in `self.state` — they will be written to disk (SQLite) in plaintext.

**Pattern for secret access in agents:**

```python
import os

class MyAgent(AgentProcess):
    async def on_start(self) -> None:
        self._api_key = os.environ["MY_API_KEY"]   # read from env at startup
```

---

## Plugin sandboxing (planned — M4.2)

In v0.3, plugins (LLM providers, tools, MCP clients) run with full process privileges. A malicious or compromised plugin can:

- Access environment variables (including other agents' secrets)
- Make arbitrary network calls
- Read/write the filesystem

M4.2 will introduce:

- Tool execution in subprocess with restricted filesystem namespaces (`seccomp`, `chroot`)
- Network egress allowlist per tool
- Per-agent credential isolation — `self.llm` and `self.tools` are scoped to the agent, not shared

---

## Audit trail

Every significant runtime event emits an OTEL span with agent identity fields:

| Span attribute | Value |
|----------------|-------|
| `civitas.agent.name` | Agent name (from supervision tree) |
| `civitas.message.sender` | Sender field from `Message` |
| `civitas.message.recipient` | Recipient field |
| `civitas.message.trace_id` | W3C trace ID for cross-agent correlation |

For a durable audit trail, configure an OTLP exporter pointing at Jaeger, Grafana Tempo, or Datadog:

```yaml
observability:
  type: otlp
  endpoint: "http://tempo.internal:4317"
```

Spans are emitted non-blockingly (`SpanQueue.put_nowait`) — exporter latency does not affect agent throughput.

---

## Security posture by deployment level

| Level | Transport | Authentication | Encryption | Audit |
|-------|-----------|----------------|------------|-------|
| 1 — single process | InProcess | None (implicit) | None | OTEL spans |
| 2 — multi-process | ZMQ | None (v0.3) / CURVE (M4.2) | None (v0.3) / CURVE (M4.2) | OTEL spans |
| 3 — distributed | NATS | Credential file | TLS (server config) | OTEL spans |
| 4 — external traffic | NATS + HTTP Gateway | API key / JWT middleware | TLS (gateway) | OTEL spans + access log |

The recommended production posture for any deployment handling sensitive data is **Level 3 or 4 with M4.2 hardening applied**.
