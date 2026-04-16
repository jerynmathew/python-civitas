# Supervision

Supervision is Civitas's core fault-tolerance mechanism. This document covers everything about configuring and composing supervisors: restart strategies, backoff policies, escalation chains, nested trees, and heartbeat-based monitoring for remote agents.

---

## The "let it crash" principle

Civitas's supervision model is borrowed from Erlang/OTP, and its central idea is counterintuitive: **don't try to recover from errors inside the failing code**. Let the process crash cleanly. A supervisor — which is separate from the failing code — decides what to do.

This separation matters because:

- Error handling inside `handle()` is speculative. You can't always predict what state the agent is in after an error.
- A supervisor has a broader view: it knows the system's current restart rate, its history, and the relationships between processes.
- Defensive error-handling code in `handle()` tends to hide bugs. Crashing loudly surfaces them.

The practical implication: keep `on_error()` simple. Return `ErrorAction.ESCALATE` unless you have a specific, well-understood retry policy. Let the supervisor do its job.

---

## Supervisor constructor

```python
Supervisor(
    name="root",
    children=[...],                # AgentProcess or Supervisor instances
    strategy="ONE_FOR_ONE",        # or ONE_FOR_ALL, REST_FOR_ONE
    max_restarts=3,                # crash limit within restart_window
    restart_window=60.0,           # sliding window in seconds
    backoff="CONSTANT",            # or LINEAR, EXPONENTIAL
    backoff_base=1.0,              # initial delay in seconds
    backoff_max=60.0,              # maximum delay cap in seconds
)
```

All parameters have defaults. A minimal supervisor:

```python
Supervisor("root", children=[MyAgent("agent")])
```

---

## Restart strategies

### ONE_FOR_ONE

When a child crashes, restart **only that child**. All other children continue running unaffected.

```mermaid
graph TD
    S["Supervisor\nONE_FOR_ONE"]
    S --> A["agent-a\n✓ running"]
    S --> B["agent-b\n✗ crashed → ↻ restarting"]
    S --> C["agent-c\n✓ running"]

    style B fill:#7f1d1d,color:#fff
```

**Use when:** Children are independent — a crash in one does not invalidate the state of others.

**Examples:**
- A pool of worker agents each handling independent requests
- Multiple API integrations running in parallel
- Stateless agents that process one message at a time

```python
Supervisor(
    "workers",
    strategy="ONE_FOR_ONE",
    children=[
        Worker("worker-1"),
        Worker("worker-2"),
        Worker("worker-3"),
    ],
)
```

---

### ONE_FOR_ALL

When any child crashes, **stop and restart all children**.

```mermaid
graph TD
    S["Supervisor\nONE_FOR_ALL"]
    S --> A["agent-a\n↻ restarting"]
    S --> B["agent-b\n✗ crashed → ↻ restarting"]
    S --> C["agent-c\n↻ restarting"]

    style A fill:#6b4c11,color:#fff
    style B fill:#7f1d1d,color:#fff
    style C fill:#6b4c11,color:#fff
```

**Use when:** Children share mutable state or maintain synchronized positions. If one crashes, the others' state is no longer valid and they must start fresh.

**Examples:**
- A producer and consumer that share a queue reference
- A writer and a cache agent that must stay synchronized
- A leader and followers in a coordinated protocol

```python
Supervisor(
    "pipeline",
    strategy="ONE_FOR_ALL",
    children=[
        Producer("producer"),
        Consumer("consumer"),
    ],
)
```

---

### REST_FOR_ONE

When a child crashes, restart that child **and all children that were started after it** (younger siblings). Children started earlier are unaffected.

```mermaid
graph TD
    S["Supervisor\nREST_FOR_ONE"]
    S --> A["stage-1\n✓ unaffected\n(started first)"]
    S --> B["stage-2\n✗ crashed → ↻\n(restarting)"]
    S --> C["stage-3\n↻ restarting\n(younger sibling)"]

    style B fill:#7f1d1d,color:#fff
    style C fill:#6b4c11,color:#fff
```

**Use when:** You have a pipeline where later stages depend on earlier ones. If stage-2 crashes, stage-3 is receiving invalid input and must also restart.

**Examples:**
- Sequential processing stages: fetcher → parser → indexer
- A connection stage followed by one or more dependent processing stages

```python
Supervisor(
    "pipeline",
    strategy="REST_FOR_ONE",
    children=[
        Fetcher("fetcher"),      # if fetcher crashes, parser and indexer also restart
        Parser("parser"),        # if parser crashes, indexer also restarts
        Indexer("indexer"),      # if indexer crashes, only indexer restarts
    ],
)
```

---

## Backoff policies

Between each restart attempt, the supervisor waits a calculated delay. This prevents retry storms when a downstream dependency is unavailable.

| Policy | Formula | Example (base=1.0s, attempts 1–5) |
|---|---|---|
| `CONSTANT` | `base` | 1s, 1s, 1s, 1s, 1s |
| `LINEAR` | `base × attempt` | 1s, 2s, 3s, 4s, 5s |
| `EXPONENTIAL` | `base × 2^(attempt−1)` ± jitter | ~1s, ~2s, ~4s, ~8s, ~16s |

`EXPONENTIAL` adds up to 25% random jitter per attempt to prevent multiple agents from retrying in lockstep.

All delays are capped at `backoff_max` (default 60s).

```python
Supervisor(
    "root",
    backoff="EXPONENTIAL",
    backoff_base=0.5,    # start at 0.5s
    backoff_max=30.0,    # cap at 30s
    children=[...],
)
```

**Choosing a policy:**

- **Development / tests:** `CONSTANT` with a short base (e.g. `backoff_base=0.1`) so restarts are fast and visible.
- **Production with transient failures:** `EXPONENTIAL` — gives downstream services time to recover.
- **Production with predictable failures:** `LINEAR` — gradual back-off without the compounding of exponential.

---

## Sliding window rate limiting

The supervisor counts crashes within a sliding time window. If `max_restarts` crashes occur within `restart_window` seconds, the supervisor escalates instead of restarting.

```
max_restarts=3, restart_window=60.0

t=0s   → crash 1  →  1 crash in window  →  restart
t=10s  → crash 2  →  2 crashes in window →  restart
t=20s  → crash 3  →  3 crashes in window →  restart
t=30s  → crash 4  →  4 crashes in window →  ESCALATE
```

But:
```
t=0s   → crash 1  →  1 crash in window  →  restart
t=10s  → crash 2  →  2 crashes in window →  restart
t=70s  → crash 3  →  2 crashes in window (t=0 has expired) →  restart
t=80s  → crash 4  →  3 crashes in window →  restart
```

The window slides continuously — it's not a fixed interval that resets.

**Tuning guidance:**

| Scenario | `max_restarts` | `restart_window` |
|---|---|---|
| Transient network errors expected | 5–10 | 60s |
| Bugs should surface quickly | 2–3 | 30s |
| Long-running critical process | 3 | 300s |
| Development / testing | 10+ | 60s |

---

## Escalation chain

When a supervisor exhausts its restart budget, it escalates to its own parent supervisor. The parent treats the child supervisor as if it were a crashed agent and applies its own restart strategy.

```mermaid
graph TD
    Root["root supervisor\nONE_FOR_ONE\nmax_restarts=2"]
    Child["research_sup\nONE_FOR_ONE\nmax_restarts=3"]
    Agent["web_researcher"]

    Root -->|monitors| Child
    Child -->|monitors| Agent

    Agent -->|"crash #1 → restart"| Child
    Agent -->|"crash #2 → restart"| Child
    Agent -->|"crash #3 → restart"| Child
    Agent -->|"crash #4 → max_restarts exceeded"| Child
    Child -->|"escalate: treats self as crashed"| Root
    Root -->|"restart research_sup + all its children"| Child

    style Agent fill:#7f1d1d,color:#fff
    style Child fill:#6b4c11,color:#fff
```

If the root supervisor also exhausts its budget, the process stops permanently and an error is logged. There is no escalation above the root.

---

## Nested supervisors

Supervisors can contain other supervisors. This is the primary tool for building complex fault-tolerance topologies where different subsystems have different failure policies.

```python
Runtime(
    supervisor=Supervisor(
        "root",
        strategy="ONE_FOR_ONE",
        max_restarts=2,
        children=[
            # Research subsystem — failures isolated here
            Supervisor(
                "research_sup",
                strategy="ONE_FOR_ONE",
                max_restarts=5,
                backoff="EXPONENTIAL",
                children=[
                    WebResearcher("web_researcher"),
                    DocSearcher("doc_searcher"),
                ],
            ),
            # Execution subsystem — all-or-nothing restart
            Supervisor(
                "execution_sup",
                strategy="ONE_FOR_ALL",
                max_restarts=3,
                children=[
                    ApiCaller("api_caller"),
                    DbWriter("db_writer"),
                ],
            ),
            # Standalone agent at root level
            Orchestrator("orchestrator"),
        ],
    )
)
```

With this tree:

- `web_researcher` crashes → `research_sup` restarts it → `execution_sup` and `orchestrator` unaffected
- `api_caller` crashes → `execution_sup` restarts both `api_caller` and `db_writer` → `research_sup` and `orchestrator` unaffected
- `research_sup` exhausts its budget → escalates to `root` → `root` restarts `research_sup` (and its children)

From YAML:

```yaml
supervision:
  name: root
  strategy: ONE_FOR_ONE
  max_restarts: 2
  children:
    - supervisor:
        name: research_sup
        strategy: ONE_FOR_ONE
        max_restarts: 5
        backoff: EXPONENTIAL
        children:
          - agent: { name: web_researcher, type: myapp.WebResearcher }
          - agent: { name: doc_searcher,   type: myapp.DocSearcher }
    - supervisor:
        name: execution_sup
        strategy: ONE_FOR_ALL
        max_restarts: 3
        children:
          - agent: { name: api_caller, type: myapp.ApiCaller }
          - agent: { name: db_writer,  type: myapp.DbWriter }
    - agent: { name: orchestrator, type: myapp.Orchestrator }
```

---

## Heartbeat monitoring for remote agents

When agents run in separate OS processes (ZMQ or NATS transport), the supervisor cannot monitor them via asyncio task callbacks — the tasks are in a different process. Instead, it uses periodic heartbeats.

```mermaid
sequenceDiagram
    participant Sup as Supervisor
    participant Bus as MessageBus
    participant Worker as Worker Process
    participant Agent as Remote Agent

    loop every heartbeat_interval
        Sup->>Bus: _agency.heartbeat → agent-name
        Bus->>Worker: route
        Worker->>Agent: deliver
        Agent-->>Bus: _agency.heartbeat_ack
        Bus-->>Sup: ack received

        alt ack not received within heartbeat_timeout
            Sup->>Sup: missed_heartbeats[agent] += 1
            alt missed >= threshold
                Sup->>Bus: _agency.restart → worker
                Worker->>Agent: restart
            end
        end
    end
```

Heartbeat monitoring is configured per remote child via `add_remote_child()`, or automatically when loading a topology YAML with `process: worker` entries:

```python
supervisor.add_remote_child(
    name="remote_agent",
    heartbeat_interval=5.0,        # ping every 5 seconds
    heartbeat_timeout=2.0,         # wait up to 2 seconds for ack
    missed_heartbeats_threshold=3, # restart after 3 consecutive misses
)
```

In YAML topology:

```yaml
- agent:
    name: remote_agent
    type: myapp.RemoteAgent
    process: worker            # runs in a Worker process
    heartbeat_interval: 5.0
    heartbeat_timeout: 2.0
    missed_heartbeats_threshold: 3
```

The backoff and restart strategy configured on the parent supervisor apply to remote restarts too — only the detection mechanism differs.

---

## Supervision and error actions

The supervision strategy only applies when an agent returns `ErrorAction.ESCALATE` from `on_error()`, or when `on_error()` itself raises an exception. Other error actions are handled inside the agent:

| `ErrorAction` | Who handles it | Supervisor involved? |
|---|---|---|
| `RETRY` | Runtime re-delivers the message | No |
| `SKIP` | Runtime discards the message | No |
| `STOP` | Runtime shuts down the agent gracefully | No |
| `ESCALATE` | Agent crashes → **supervisor takes over** | **Yes** |

The default `on_error()` returns `ESCALATE`. Override it when you have a meaningful retry policy:

```python
async def on_error(self, error: Exception, message: Message) -> ErrorAction:
    if isinstance(error, RateLimitError) and message.attempt < 3:
        return ErrorAction.RETRY     # re-deliver, supervisor not involved
    if isinstance(error, ValidationError):
        return ErrorAction.SKIP      # bad message, move on
    return ErrorAction.ESCALATE      # anything else: crash and let supervisor decide
```

---

## Observability

Every supervisor restart emits an OTEL span with the following attributes:

| Attribute | Value |
|---|---|
| `civitas.supervisor` | Supervisor name |
| `civitas.child` | Name of the restarted child |
| `civitas.restart_count` | Restart number for this child |
| `civitas.strategy` | `ONE_FOR_ONE` / `ONE_FOR_ALL` / `REST_FOR_ONE` |
| `civitas.error` | Exception string that caused the restart |

These spans are linked to the agent's trace, so you can see the full causal chain: which message triggered the crash, how many restarts occurred, and when the agent recovered.

---

## Common patterns

**Pattern: Fast restarts in development, conservative in production**

```python
import os

Supervisor(
    "root",
    max_restarts=10 if os.getenv("ENV") == "dev" else 3,
    restart_window=60.0,
    backoff="CONSTANT" if os.getenv("ENV") == "dev" else "EXPONENTIAL",
    backoff_base=0.05 if os.getenv("ENV") == "dev" else 1.0,
    children=[...],
)
```

**Pattern: Isolate an unreliable integration**

Put unreliable agents under their own supervisor with a generous restart budget, separate from the rest of the system:

```python
Supervisor("root", strategy="ONE_FOR_ONE", children=[
    Supervisor(
        "flaky_api_sup",
        strategy="ONE_FOR_ONE",
        max_restarts=10,
        backoff="EXPONENTIAL",
        children=[FlakyApiAgent("flaky_api")],
    ),
    StableAgent("stable"),
])
```

`stable` is completely unaffected by however many times `flaky_api` crashes.

**Pattern: Circuit breaker via max_restarts**

Set `max_restarts` low on purpose to stop hammering a downstream service that is down. Let it escalate to the root, which restarts the entire subsystem after a longer backoff:

```python
Supervisor("root", strategy="ONE_FOR_ONE", backoff="EXPONENTIAL", backoff_base=30.0, children=[
    Supervisor(
        "db_sup",
        strategy="ONE_FOR_ONE",
        max_restarts=2,        # fail fast
        restart_window=30.0,
        backoff="CONSTANT",
        backoff_base=1.0,
        children=[DbAgent("db")],
    ),
])
```

After 2 failures in 30 seconds, `db_sup` escalates to `root`, which waits ~30s (exponential base) before restarting the subsystem.
