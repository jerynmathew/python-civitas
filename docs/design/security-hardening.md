# Design: Runtime Security Hardening (M4.2)

**Status:** Proposal — v0.4
**Author:** Jeryn Mathew Varghese
**Last updated:** 2026-05

---

## Motivation

M4.3 produced a STRIDE threat model identifying **10 HIGH** and **8 MEDIUM** risks in the Civitas runtime. Most of those findings explicitly defer their mitigation to M4.2. Today the runtime ships with:

- **No transport encryption.** ZMQ messages traverse loopback as raw msgpack ([civitas/transport/zmq.py:1-284](../../civitas/transport/zmq.py)). NATS connects without client TLS. Cross-host deployments are not safe.
- **No message authentication.** `Message.sender` is a string field set by the sender and never verified ([civitas/messages.py](../../civitas/messages.py)). Any agent can spoof any other agent (Spoofing, HIGH).
- **Plaintext secrets in YAML.** `from_config()` does not substitute env vars; API keys must be hardcoded into topology files or wrapped at the deployment layer ([civitas/runtime.py:100-317](../../civitas/runtime.py)).
- **No per-agent credential scope.** Plugins (LLM providers, tools) read env vars or take config dicts at instantiation; every agent shares the same credentials.
- **No tool sandboxing.** MCP tools are executed as subprocesses with the runtime's full privileges ([civitas/mcp/tool.py:44-67](../../civitas/mcp/tool.py)).
- **No structured audit log.** OTel spans cover observability but are not designed as a tamper-evident audit trail.

M4.2 closes these gaps. It is the implementation arm of the threat model.

---

## Scope

**In scope:** mTLS for ZMQ + NATS, message signing with stable agent identity, env-var secret substitution + per-agent credential scoping, sandboxed tool execution, structured audit log.

**Out of scope (deferred):**

- HSM / TPM-backed keys (post-v1.0)
- Fine-grained ACL DSL (M4.4 Capability-Aware Registry overlaps; revisit once that lands)
- Encrypted `StateStore` at rest (separate effort — can move to v0.5)
- PKI/CA integration (deployment-layer concern; we ship key generation but not certificate issuance)
- HTTPGateway authentication middleware (already a documented integration point; users plug in their own JWT/OIDC)

---

## Design Decisions

### D1 — Security is opt-in per topology, not a global flag

A topology declares a `security:` block. When omitted, the runtime behaves exactly as today (in-process, no signing, no TLS) so existing demos and tests keep working. When present, every applicable layer is hardened.

```yaml
security:
  identity:
    mode: auto                  # auto-generate Ed25519 keypair per agent at startup
    # mode: provisioned         # load from key_dir
    # key_dir: /etc/civitas/keys
  signing:
    enabled: true
    algorithm: ed25519
    require_verification: true  # reject unsigned messages
  transport:
    tls_cert: /etc/civitas/server.crt
    tls_key:  /etc/civitas/server.key
    tls_ca:   /etc/civitas/ca.crt
  audit:
    enabled: true
    sink: file
    path: /var/log/civitas/audit.jsonl
```

Rationale: backwards compatibility is non-negotiable for v0.4. Forcing global migration would break every existing topology. Per-topology opt-in lets production deployments harden without churning the entire ecosystem.

### D2 — Ed25519 keypairs per agent (not HMAC)

Each agent holds an Ed25519 signing keypair. Messages carry `(signer_id, signature)`. Verifiers need only the public key registry, not a shared secret. This matches the agent identity model (each agent is a distinct principal) and avoids the key distribution problem of HMAC (every verifier needs every secret).

| Choice | Why |
|---|---|
| **Ed25519** over HMAC-SHA256 | Public-key model fits the multi-agent topology; verifiers don't hold sender secrets |
| **Ed25519** over RSA/ECDSA | Faster signing/verification, smaller signatures (64 bytes), no parameter pitfalls |
| **PyNaCl** library | Audited, single-purpose, already widely used in distributed systems |

The runtime auto-generates keypairs on first start (`mode: auto`) and stashes them in a configurable key directory. Production deployments use `mode: provisioned` and bring their own keys.

### D3 — Sign the envelope, not the payload

Signing happens at the serializer layer, **after** `Message.to_dict()` but **before** msgpack encoding. The wire format wraps the message:

```python
{
    "v": 2,
    "msg": <serialized message dict>,
    "sig": {"signer": "agent_name", "alg": "ed25519", "value": <bytes>, "nonce": <bytes>}
}
```

Verification at deserialize-time recovers the message dict, verifies the signature against the registered public key for `signer`, and rejects on mismatch (raises `SignatureError`, a new `CivitasError` subclass).

Rationale: signing the envelope (not just the payload) protects routing fields (`sender`, `recipient`, `correlation_id`) from tampering. The schema bumps from v1 to v2; v1 messages remain readable by deserializers when `require_verification: false`.

### D4 — ZMQ CURVE for ZMQ; TLS + nkeys for NATS

| Transport | Mechanism | Why |
|---|---|---|
| **ZMQ** | CURVE (libsodium, built into pyzmq) | Native ZMQ support, no proxy changes, mature and battle-tested |
| **NATS** | TLS + nkeys (Ed25519-based subject auth) | NATS-native, integrates with their permissions model |
| **InProcess** | No-op | Single-process; no wire to protect |

The ZMQ proxy needs CURVE server keys; each Worker gets a CURVE client keypair. NATS clients receive an `nkey` seed and TLS material. Both are read from the `security.transport` block.

The `security` block can also be partially configured: `signing.enabled: true` works without TLS (e.g., on trusted networks where the threat is rogue agents, not network adversaries).

### D5 — Env-var substitution in YAML; secrets never in source

`Runtime.from_config()` walks the parsed YAML and resolves `${VAR_NAME}` patterns against `os.environ`. Unset variables raise a clear error. This is the **only** substitution syntax — no default values, no shell expansion, no nested expressions. The substitution layer is independent of any specific secrets manager: deployment owners use whatever surfaces env vars (Kubernetes secrets, Docker secrets, Vault sidecar, AWS Secrets Manager via their CLI).

```yaml
plugins:
  models:
    - type: anthropic
      config:
        api_key: ${ANTHROPIC_API_KEY}
```

A separate optional `civitas.secrets.SecretsProvider` protocol (with file/env/Vault implementations) lets advanced users plug in dynamic resolution. The default implementation is the env-var substituter described above.

### D6 — Per-agent credential scope via plugin handles

Plugins are instantiated once per process today. To scope credentials per agent without refactoring every plugin, introduce **plugin handles**: an agent calls `self.llm("anthropic")` instead of receiving an injected `ModelProvider`. The handle resolves the right credential set at call time based on `topology.yaml`:

```yaml
agents:
  - name: research_agent
    credentials:
      anthropic: ${RESEARCH_AGENT_ANTHROPIC_KEY}
  - name: writer_agent
    credentials:
      anthropic: ${WRITER_AGENT_ANTHROPIC_KEY}
```

When `agent.credentials.<plugin>` is unset, the handle falls back to the global plugin instance (current behaviour). This is opt-in and additive — existing agents keep working unchanged.

### D7 — Tool execution sandbox: bubblewrap on Linux, warn elsewhere

MCP servers spawn as subprocesses today. M4.2 wraps that subprocess with [`bubblewrap`](https://github.com/containers/bubblewrap) on Linux: read-only root filesystem, no network unless declared, scratch tmpfs for `/tmp`. The sandbox profile is per-MCP-server in YAML:

```yaml
plugins:
  mcp:
    - name: shell_tool
      command: /usr/local/bin/shell_mcp
      sandbox:
        enabled: true
        network: deny           # deny | allow | <allowlist>
        filesystem:
          - /workspace:rw
          - /etc/ssl/certs:ro
```

On non-Linux platforms (or when `bwrap` is missing), the runtime logs a HIGH-severity warning at startup and runs unsandboxed. We do **not** ship a Python-level sandbox (no real isolation in-process). Stronger isolation (gVisor, Firecracker) is out of scope.

### D8 — Audit log is separate from OTel

OTel is for debugging and observability — its spans drop, sample, and export to user-controlled backends. An audit log has different requirements: append-only, never sampled, locally durable, structured for compliance review.

M4.2 ships a `civitas.audit` module that emits structured events:

```python
class AuditEvent(TypedDict):
    timestamp: str        # ISO8601 with UTC offset
    event_type: str       # auth.deny | sign.verify_fail | sandbox.violation | secret.access | ...
    actor: str            # agent name
    target: str | None    # message recipient, tool name, secret name
    result: str           # allow | deny | error
    metadata: dict        # event-specific
```

Default sink is `JsonlFileSink` — newline-delimited JSON, fsync-on-write. A `NullSink` exists for tests. Users can plug `SyslogSink`, `OtlpSink`, or custom sinks via `civitas.audit.AuditSink` protocol.

Audit events are emitted at well-defined chokepoints:
- `MessageBus.route()` — on signature failure or denied message
- `MCPTool.execute()` — on every tool invocation (allow + result code)
- Sandbox wrapper — on policy violation
- Secret access — when a plugin handle resolves a credential

### D9 — Performance discipline

Security primitives have measurable cost. Three rules keep that cost predictable:

1. **InProcess signing is a no-op.** When both sender and receiver are in the same OS process, signature verification adds nothing — the OS already provides isolation. The `Signer` for InProcess transport returns a sentinel signature; the verifier accepts it without computing Ed25519. Cross-process and cross-host transports always sign and verify.

2. **Audit log batches by default.** `JsonlFileSink` buffers events in memory and fsyncs every 100ms or every 100 events, whichever comes first. A `sync_writes: true` option exists for compliance-strict deployments but is **off by default**. Per-event fsync at high throughput drops the bus to <1k msg/sec — the one configuration that would make security feel painful.

3. **CI benchmark gate.** A `pytest-benchmark` test measures `MessageBus.route()` throughput on InProcess transport with signing+audit enabled vs. baseline. CI fails if the regression exceeds **30%**. This makes performance regressions visible at PR time rather than after release.

Concrete numbers (modern x86, single core):

| Operation | Cost | Notes |
|---|---|---|
| Ed25519 sign | ~30–50µs | Sender pays |
| Ed25519 verify | ~80–120µs | Receiver pays — verify is slower than sign |
| ChaCha20-Poly1305 (TLS/CURVE) | ~5µs / KB | Negligible at message sizes |
| Audit emit (batched) | ~10µs | Default mode |
| Audit emit (sync fsync) | 1–10ms | Only when `sync_writes: true` |
| Plugin handle resolution | ~100ns | Dict lookup |

For LLM-orchestration workloads, total per-message overhead is **~300µs cross-process, 0µs in-process** — invisible against a 500ms–5s LLM round-trip. For high-throughput pipelines (>10k msg/sec/core sustained), signing on cross-process transports becomes the bottleneck; users can disable signing on trusted transports via `signing.enabled: false`.

---

## Phasing

M4.2 is too big for one PR. It splits into five sub-milestones, each independently shippable and testable:

| Sub-milestone | Scope | Depends on |
|---|---|---|
| **M4.2a — Identity & Signing** | Ed25519 keypairs, signed envelopes, `SignatureError`, public key registry, `security:` YAML block | — |
| **M4.2b — Transport mTLS** | ZMQ CURVE, NATS TLS + nkeys, transport config plumbing | M4.2a (shares identity store) |
| **M4.2c — Credential Isolation** | `${VAR}` env substitution, `SecretsProvider` protocol, per-agent credential scope, plugin handles | — (independent) |
| **M4.2d — Tool Sandbox** | Bubblewrap wrapper for MCP subprocesses, sandbox YAML schema, platform fallback warnings | — (independent) |
| **M4.2e — Audit Log** | `civitas.audit` module, default JsonlFileSink, integration at chokepoints | M4.2a (auth events use signer_id) |

Recommended order: **a → c → d → e → b**. Identity and signing unlock the audit log's notion of an authenticated actor; credentials and sandbox harden the local-trust scenarios most users hit first; transport mTLS lands last because it requires the most operational change (cert provisioning).

---

## Test Plan

Each sub-milestone ships with:

- **Unit tests** for primitives (sign/verify roundtrip, env substitution edge cases, sandbox config parsing)
- **Integration tests** at the MessageBus level (signed message accepted, unsigned rejected when required, replay rejected)
- **Negative tests** — every threat model HIGH item gets a regression test that proves the mitigation works (e.g., spoofed sender → rejected; tampered payload → rejected; unauthorized tool path → sandbox blocks)
- **Coverage target** ≥90% on new code; no drop below current 92% suite-wide

A new test directory: `tests/security/` for cross-cutting tests that combine multiple primitives.

---

## Open Questions

- **Q1 — Key directory format:** OpenSSH-style (`id_ed25519`, `id_ed25519.pub`) for familiarity, or a custom JSON manifest for richer metadata (rotation date, allowed roles)? Recommend OpenSSH for v0.4.
- **Q2 — Replay protection scope:** signing alone doesn't prevent replay. Do we ship a `seen_nonces` cache (LRU, bounded), or treat replay as out-of-scope and document it as a TLS-layer concern? Recommend ship a bounded cache — it's a common-class threat and the cost is low.
- **Q3 — Audit log rotation:** ship logrotate-friendly behaviour (close+reopen on SIGHUP), or include rotation in the sink? Recommend SIGHUP — keeps the sink simple and lets ops use existing tooling.
- **Q4 — Sandbox on macOS/Windows:** is "warn and run unsandboxed" acceptable, or should we refuse to start unsandboxed when `sandbox.enabled: true`? Recommend refuse — fail-closed is the right default for a security feature.
- **Q5 — Backwards-compatible signing:** when a topology has `signing.enabled: true` but receives an unsigned message (e.g., from an older agent), do we reject (strict) or log+accept (compat mode for rolling upgrades)? Recommend strict by default, with a `signing.allow_unsigned: true` escape hatch documented as transitional.

---

## Risks

- **Operational complexity.** mTLS + key rotation + sandbox profiles add significant deployment burden. Mitigation: ship sane defaults, a `civitas security init` CLI command to scaffold keys/configs, and recipes in `docs/security/recipes.md`.
- **Performance.** Cross-process round-trip adds ~300µs (Ed25519 sign + verify on both sides; verify is the dominant ~80–120µs cost). For LLM-orchestration workloads this is invisible against the LLM call itself (500ms–5s). For high-throughput pipelines sustaining >10k msg/sec/core, signing becomes the bottleneck. The audit log is the bigger hidden risk: synchronous fsync per event would drop the bus to <1k msg/sec. Mitigations are codified in **D9 — Performance discipline**: InProcess transport short-circuits signing, audit log batches by default (100ms or 100 events), and a CI benchmark gate fails any change that regresses InProcess throughput by >30%.
- **Bubblewrap availability.** Not on macOS, optional on most Linux distros. Mitigation: clear startup warnings, documented install commands per distro, refuse-to-start mode for production.
- **Scope creep.** "Security" is unbounded; M4.2 explicitly lists what's out of scope above. Resist additions during implementation — capture them as v0.5+ candidates.

---

## Next steps

1. Resolve Q1–Q5 with the user.
2. Update `docs/milestones.md` M4.2 deliverables to match the five sub-milestone breakdown.
3. Land **M4.2a — Identity & Signing** first; it's the foundation for everything else.
