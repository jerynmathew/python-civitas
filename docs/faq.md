# FAQ

Common questions and objections, answered directly.

---

## "Why not just use Temporal?"

**Temporal** is a durable workflow engine. It checkpoints every step of a workflow to a database and can replay from any point after a failure. That durability is powerful, but it comes with a significant cost:

- **A separate Temporal cluster** must be running (the Temporal server, plus a database — typically Postgres or Cassandra)
- **All function arguments and return values** must be serializable to Temporal's data format
- **Workflow and activity code** must be written in Temporal's programming model — no arbitrary Python, no async generators, no shared state between activities
- **Latency per step** is in the tens-to-hundreds of milliseconds because every transition writes to the database
- **Local development** requires running a local Temporal server or using the Temporal Cloud

Agency is designed for the common case: **LLM-backed agents that mostly do I/O**. The failure mode is "an agent crashes between two LLM calls" — not "a 10,000-step workflow must resume exactly where it left off." Agency's supervision tree restarts the crashed agent in milliseconds, optionally restoring its last `self.checkpoint()` from SQLite. No external server required.

**Use Temporal when:**
- You have long-running workflows measured in days or weeks
- Exact replay semantics are a legal or compliance requirement
- You need cross-language workflow coordination

**Use Agency when:**
- You want fault tolerance with zero infrastructure overhead
- Your agents are I/O-bound (LLM calls, API calls, tool use)
- You want to start locally and scale to distributed without rewriting

---

## "Why not LangGraph with checkpointing?"

**LangGraph** is a graph-based orchestration library for building multi-agent LLM applications. It supports checkpointing via its `MemorySaver` / `SqliteSaver` / `PostgresSaver` interfaces. It is a good tool for workflows that map cleanly to a directed graph.

The differences:

| | LangGraph | Agency |
|---|---|---|
| **Mental model** | Graph of nodes and edges | Supervision tree of actor processes |
| **Fault tolerance** | Manual retry logic per node | Automatic supervisor restart with backoff |
| **Transport** | In-process Python calls | Pluggable: asyncio → ZMQ → NATS |
| **Agent isolation** | All nodes share the same process | Agents can run in separate OS processes or machines |
| **Scalability** | Single Python process | Level 1 → 4 ladder, same code |
| **Observability** | Manual instrumentation | Automatic OTEL spans for every message and LLM call |

LangGraph gives you more control over the graph structure but leaves fault tolerance, scaling, and observability to you. Agency makes those properties automatic and provides a path from single-process development to multi-machine production.

LangGraph agents can also be wrapped in Agency via `LangGraphAgent` — you get Agency's supervision and transport on top of a compiled LangGraph graph. See [Adapters](adapters.md).

---

## "Why not CrewAI?"

**CrewAI** is a high-level framework for defining teams of agents with roles, goals, and backstories. It is designed for ease of use and rapid prototyping.

Agency is a lower-level runtime with different priorities:

| | CrewAI | Agency |
|---|---|---|
| **Abstraction level** | High — roles, goals, crews | Low — processes, supervisors, mailboxes |
| **Control** | Declarative, opinionated | Explicit, composable |
| **Fault tolerance** | None built-in | Supervisor tree with restart strategies |
| **Deployment** | Single Python process | InProcess → ZMQ → NATS → Docker |
| **Transport** | LLM routing only | Any message type, any transport |
| **Observability** | Limited | Full OTEL traces per message, LLM call, tool |

CrewAI is better for "define a team and let them work." Agency is better for "build a reliable system where specific agents have specific responsibilities and must not stay down."

Agency and CrewAI are not mutually exclusive. A CrewAI crew can run inside an `AgentProcess`, supervised by Agency's tree.

---

## "Isn't this what Akka does?"

Yes — conceptually. Agency is the BEAM/Akka actor model applied to Python LLM agents.

**Akka** (and Erlang/OTP before it) pioneered:
- Supervision trees with restart strategies
- Location-transparent message passing
- "Let it crash" fault tolerance
- Per-actor state isolated from other actors

Agency brings the same ideas to Python:

| | Akka | Agency |
|---|---|---|
| **Language** | Scala/Java | Python |
| **License** | BSL 1.1 (Business Source) | Apache 2.0 |
| **Pricing** | Enterprise subscription for production use | Free, open-source |
| **Runtime** | JVM with lightweight threads | CPython with asyncio |
| **Message format** | JVM objects | Msgpack (binary) or JSON |
| **Deployment** | Akka Cluster | InProcess / ZMQ / NATS |
| **LLM integration** | None built-in | ModelProvider, ToolProvider, StateStore |

Akka Cluster's BSL license means production use requires a commercial agreement after the first year. Agency is Apache 2.0 — use it in production, fork it, build on it.

If you come from Erlang/OTP or Akka, Agency's mental model will feel immediately familiar. The primitives map directly: `AgentProcess` ↔ GenServer, `Supervisor` ↔ Supervisor, ONE_FOR_ONE/ONE_FOR_ALL/REST_FOR_ONE ↔ the same three OTP strategies.

---

## "Will the GIL hurt performance?"

For LLM-backed agents: **no**.

The GIL only blocks Python threads from executing Python bytecode concurrently. It does not block:
- `asyncio` I/O — awaiting HTTP responses, NATS messages, database queries
- Native extension I/O — the Anthropic SDK, aiohttp, asyncpg all release the GIL during network I/O

An agent waiting for a Claude response spends 99% of its time in C-level network I/O with the GIL released. A 16-agent system on InProcessTransport with all agents making concurrent LLM calls will saturate your token rate limit, not Python's scheduler.

**When the GIL does matter:**

- CPU-bound Python code: matrix operations in pure Python, text tokenization in Python, etc.
- GPU inference in Python (though PyTorch releases the GIL for CUDA operations)

For those workloads, move the affected agents to Level 2 (ZMQ) to give them their own OS process and their own GIL. Agency's `process: worker` field in the topology makes this a one-line change.

---

## "Can I use Agency with my existing framework?"

Yes. Agency provides adapters for common frameworks:

**LangGraph** — wrap a compiled `StateGraph` in a `LangGraphAgent`. The graph runs inside Agency's message loop, supervised by the tree, with full OTEL trace propagation.

**OpenAI Agents SDK** — wrap an OpenAI `Agent` in an `OpenAIAgent`. Supervision, transport, and observability from Agency wrap the OpenAI agent's tool-use loop.

See [Adapters](adapters.md) for examples.

More generally, any Python object can be called from inside an `AgentProcess.handle()`. If your existing code is an async function, a class with methods, or an API client, you call it directly — Agency does not restrict what you do inside an agent.

---

## "Agency vs. a plain asyncio task runner — what's the difference?"

`asyncio.create_task()` is a primitive. It creates a coroutine that runs concurrently with other tasks. If it raises an exception and you don't catch it, the exception is silently swallowed (logged as an "unhandled exception in task" at Python 3.11+, but nothing restarts the task).

Agency adds:

**Automatic fault recovery.** When an agent raises an unhandled exception, its supervisor restarts it according to the configured strategy and backoff policy. You don't write try/except in every handler — you let it crash and let the supervisor handle it.

**Mailbox isolation.** Each agent has a bounded mailbox. If an agent is slow, its mailbox fills up and backpressure is applied to the sender — the sender blocks rather than flooding the slow agent. `asyncio.create_task()` has no concept of backpressure.

**Location transparency.** A message to `researcher` is the same line of code whether `researcher` is a local asyncio task, a process on the same machine, or a process on another machine. The transport is swapped in the topology YAML — agent code is unchanged.

**Named, routable agents.** Agents register by name. Any agent can send a message to any other agent by name, without holding a reference to the coroutine or task object.

**Supervised startup and shutdown.** The runtime starts agents in dependency order, waits for them to be ready, and shuts them down gracefully — draining mailboxes, flushing spans, closing connections. `asyncio.gather()` has no supervision model.

**Integrated observability.** Every message send, LLM call, and tool invocation is automatically traced as an OTEL span. With a plain task runner, you instrument everything manually.

A plain asyncio task runner is fine for a single agent that calls an LLM once. A supervision tree is the right model when you have multiple agents that must stay up, coordinate via messages, and run at different scales.

---

## "What happens to in-flight messages when an agent restarts?"

Messages in the agent's mailbox at the time of the crash are **not redelivered by default**. The supervisor restarts the agent fresh.

If you need at-least-once delivery:

- Enable NATS JetStream (`jetstream: true` in topology) — NATS persists and redelivers unacknowledged messages
- Use `await self.checkpoint()` at safe points — if the agent restarts, it resumes from the last checkpoint rather than from scratch

For most LLM workloads, losing an in-flight message is acceptable: the human or upstream agent that sent it will time out on `ask()` and retry, or the orchestrator will re-issue the task on the next run.

---

## "How does Agency handle distributed state?"

Agency does not provide a distributed state store out of the box. Each agent's `self.state` is local to that agent process.

`SQLiteStateStore` persists state to a local SQLite file — suitable for a single machine. If an agent moves between machines, its state does not follow automatically.

For distributed state:
- Use a shared backing store (Redis, PostgreSQL) by implementing a custom `StateStore` — three methods, see [Plugins](plugins.md#writing-a-custom-statestore)
- Pass state explicitly in messages between agents — Agency's message-passing model is a natural fit for this
- Use NATS JetStream key-value store via a custom plugin

Distributed state is intentionally out of scope for the core runtime. The right choice depends on your consistency requirements, and Agency's plugin protocol makes it easy to wire in whatever store fits.
