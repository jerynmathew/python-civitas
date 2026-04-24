# Design: Dynamic Agent Spawning (M4.1b)

**Status:** In design — v0.4
**Author:** Jeryn Mathew Varghese
**Last updated:** 2026-04

---

## Motivation

Civitas topologies today are fully static: all agents and supervisors are declared in YAML (or code) before the runtime starts, and the supervision tree does not change shape at runtime. This is intentional — static trees are easy to reason about, and most production systems should be static.

However, LLM-driven orchestrators often need to create specialist agents on demand and decommission them when work is done. A research orchestrator might spawn one `ResearchAgent` per query; a paralleliser might spin up N workers for a batch job. Hardcoding the worker count defeats the purpose.

Dynamic agent spawning adds a controlled runtime escape hatch: a designated `DynamicSupervisor` node can accept new children at runtime, subject to capacity and governance constraints, while keeping the rest of the tree static and predictable.

---

## OTP Analogy

Erlang separates `Supervisor` (static child spec, all three restart strategies) from `DynamicSupervisor` (starts empty, children added at runtime, ONE_FOR_ONE only). The separation exists because ONE_FOR_ALL and REST_FOR_ONE strategies depend on a fixed, ordered child list — they lose coherence when children arrive and leave dynamically. ONE_FOR_ONE is the only strategy where each child is fully independent and restart decisions never consult sibling state.

Civitas follows the same separation for the same reasons.

| OTP | Civitas |
|-----|---------|
| `Supervisor` (static) | `Supervisor` (static, all strategies) |
| `DynamicSupervisor` | `DynamicSupervisor` (starts empty, ONE_FOR_ONE only) |
| `DynamicSupervisor.start_child/2` | `self.spawn(AgentClass, name, ...)` |
| `DynamicSupervisor.terminate_child/2` | `self.despawn(name)` |

---

## Design Decisions

### D1 — `DynamicSupervisor` is a first-class node, not an extension of `Supervisor`

`Supervisor` keeps its fixed child spec and full strategy support. `DynamicSupervisor` is a separate class that starts with an empty child list and enforces ONE_FOR_ONE. This keeps both abstractions simple and avoids strategy carve-outs inside `Supervisor`.

### D2 — `DynamicSupervisor` is declared as a static child in topology YAML

The supervisor itself is a fixed, named node in the tree. What changes at runtime is its *children*. This means:

- The static tree structure is always visible in `topology show`
- The `DynamicSupervisor` appears as a named node; dynamic children hang off it
- Blast radius is contained — dynamic children cannot affect static siblings
- Shutdown is clean — stopping the `DynamicSupervisor` stops all its children in one sweep

```yaml
supervision:
  name: root
  strategy: ONE_FOR_ONE
  children:
    - name: orchestrator
      type: OrchestratorAgent
    - name: workers
      type: dynamic_supervisor
      max_children: 20
```

```
root (Supervisor, ONE_FOR_ONE)
├── orchestrator  (OrchestratorAgent, static)
└── workers       (DynamicSupervisor, static node — dynamic children)
    ├── researcher-1  (spawned at runtime)
    └── researcher-2  (spawned at runtime)
```

### D3 — `self.spawn()` targets the nearest ancestor `DynamicSupervisor`

An agent does not name the target supervisor. The runtime walks up the ancestry chain from the calling agent and finds the first `DynamicSupervisor`. If none exists in the chain, `self.spawn()` raises `SpawnError`.

Rationale:
- The topology YAML already makes the relationship explicit — the `DynamicSupervisor` is declared above the spawning agent, so reading the YAML tells you where children land
- Naming the target at the call site would duplicate information already in the topology
- Allowing agents to spawn into *remote* subtrees would couple unrelated parts of the tree; if cross-tree spawning is needed, the correct pattern is to send a message to the agent that owns that `DynamicSupervisor`

```python
# Inside OrchestratorAgent.handle()
# Finds the nearest DynamicSupervisor ancestor ("workers") automatically
agent_name = await self.spawn(ResearchAgent, name="researcher-1", config={"topic": "..."})
await self.despawn("researcher-1")
```

### D4 — `on_spawn_requested` is a governance veto hook

Before a spawn is executed, the runtime calls `on_spawn_requested(agent_class, name, config)` on the `DynamicSupervisor`. The default implementation approves all requests. Subclassing allows governance logic: rate limits, allowlists, policy checks.

```python
class GovernedWorkerPool(DynamicSupervisor):
    async def on_spawn_requested(
        self, agent_class: type, name: str, config: dict
    ) -> bool:
        if agent_class not in ALLOWLIST:
            logger.warning("Spawn of %s denied by policy", agent_class.__name__)
            return False
        return True
```

### D5 — `max_children` enforces blast radius

`DynamicSupervisor` accepts a `max_children` limit (default: unbounded). `self.spawn()` raises `SpawnError` if the limit is reached. This prevents a runaway orchestrator from exhausting system resources.

---

## Open Questions

The following questions are deferred to design sessions before implementation:

- **Q2 — Restart semantics**: When a dynamically spawned agent crashes, does the `DynamicSupervisor` restart it? Or does it stay dead and the orchestrator decides whether to re-spawn? Does the orchestrator get a notification?
- **Q3 — `on_spawn_requested` placement**: Is the hook on `DynamicSupervisor`, on `AgentProcess`, or both? Who is the right place to enforce governance?
- **Q4 — `max_concurrent_children` vs `max_children`**: Is the limit on concurrent live children, total ever spawned, or both?
- **Q5 — Despawn semantics**: Does `self.despawn()` drain the agent's mailbox first, or is it a hard stop? What happens to pending `ask()` calls into the agent?
- **Q6 — Cross-process spawning**: Does dynamic spawning work with ZMQ/NATS transports, or in-process only for v0.4?
- **Q7 — `topology show` live state**: Spawned agents are dynamic — how does `topology show` reflect the live child list vs the static YAML?

---

## API Surface (provisional)

```python
# DynamicSupervisor — topology YAML
# type: dynamic_supervisor
# max_children: 20

# AgentProcess — new methods
await self.spawn(AgentClass, name="worker-1", config={...}) -> str  # returns agent name
await self.despawn("worker-1")

# DynamicSupervisor — governance hook (override to customise)
async def on_spawn_requested(
    self, agent_class: type, name: str, config: dict[str, Any]
) -> bool: ...

# Runtime — external spawn (for non-agent callers)
await runtime.spawn("workers", ResearchAgent, name="researcher-1", config={...})
await runtime.despawn("workers", "researcher-1")
```

---

## Non-Goals (v0.4)

- Cross-process spawning (ZMQ / NATS) — deferred to v0.5
- Spawning into a remote `DynamicSupervisor` by name from an unrelated subtree
- Visual topology editor integration (M4.1 is deferred)
- Per-agent spawn quotas (only global `max_children` per `DynamicSupervisor` in v0.4)
