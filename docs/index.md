# Agency

**The production runtime for Python agents.**

Agency is an OTP-inspired agent runtime for Python. It gives your agent systems the infrastructure layer they need to run reliably in production: supervised processes that restart automatically on failure, transport-agnostic message passing that scales from a script to a distributed cluster, and zero-instrumentation observability via OpenTelemetry.

```bash
pip install python-agency
```

---

## What Agency is — and isn't

Agency is a **runtime**, not a framework. Frameworks like LangGraph, CrewAI, and the OpenAI Agents SDK define *how* you build agents. Agency defines *how they stay alive*.

It sits at the bottom of the agent stack:

```
Context layer    →  prompts, memory, RAG
Control layer    →  guardrails, HITL gates, cost limits
Runtime layer    →  Agency: lifecycle, fault tolerance, routing, observability
```

You can run Agency alongside any of those frameworks. The [LangGraph adapter](adapters.md) wraps a compiled graph as an Agency process in three lines.

---

## When to use Agency

Agency is a good fit when you need any of the following:

- **Fault tolerance** — agents that crash should restart automatically, with configurable strategies and backoff
- **Multi-agent systems** — multiple agents communicating via message passing, with named routing and backpressure
- **Scaling without rewrites** — the same agent code should run in a single process during development and across machines in production
- **Production observability** — every message, LLM call, and tool invocation traced to OTEL automatically

If you are building a simple, single-agent script that calls an LLM and exits, Agency adds more structure than you need. Start with the Anthropic SDK or OpenAI SDK directly.

---

## Five-minute start

**Hello agent** — no LLM, no dependencies beyond the core install:

```python
import asyncio
from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message

class Echo(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        return self.reply({"echo": message.payload["text"]})

async def main():
    runtime = Runtime(supervisor=Supervisor("root", children=[Echo("echo")]))
    await runtime.start()
    result = await runtime.ask("echo", {"text": "hello"})
    print(result.payload["echo"])   # hello
    await runtime.stop()

asyncio.run(main())
```

**With supervision** — agent crashes randomly, supervisor restarts it, callers never see it:

```python
import asyncio, random
from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message

class Flaky(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        if random.random() < 0.5:
            raise RuntimeError("temporary failure")
        return self.reply({"ok": True})

async def main():
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            strategy="ONE_FOR_ONE",
            max_restarts=10,
            backoff="EXPONENTIAL",
            children=[Flaky("flaky")],
        )
    )
    await runtime.start()
    for _ in range(5):
        result = await runtime.ask("flaky", {})
        print(result.payload)   # always succeeds
    await runtime.stop()

asyncio.run(main())
```

**With an LLM** — install the Anthropic provider and inject it via `Runtime`:

```bash
pip install python-agency[anthropic]
export ANTHROPIC_API_KEY=sk-...
```

```python
from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message
from agency.plugins.anthropic import AnthropicProvider

class Assistant(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        response = await self.llm.chat(
            model="claude-haiku-4-5",
            messages=[{"role": "user", "content": message.payload["question"]}],
        )
        return self.reply({"answer": response.content})

runtime = Runtime(
    supervisor=Supervisor("root", children=[Assistant("assistant")]),
    model_provider=AnthropicProvider(),
)
```

---

## Documentation

### Start here

- [Getting Started](getting-started.md) — install, hello agent, supervised agent, LLM call, OTEL tracing in sequence
- [Core Concepts](concepts.md) — the mental model: AgentProcess, Supervisor, MessageBus, Transport

### Go deeper

- [Supervision](supervision.md) — strategies, backoff, escalation chains, heartbeat monitoring
- [Messaging](messaging.md) — send, ask, broadcast, request-reply internals, backpressure
- [Transports](transports.md) — InProcess → ZMQ → NATS: the scaling ladder
- [Observability](observability.md) — automatic OTEL tracing, console exporter, Jaeger

### Reference

- [Plugins](plugins.md) — ModelProvider, ToolProvider, StateStore, writing custom plugins
- [Topology YAML](topology.md) — full schema reference, CLI commands
- [Deployment](deployment.md) — single process through containerized, step by step
- [Framework Adapters](adapters.md) — wrapping LangGraph and OpenAI SDK agents
- [Architecture](architecture.md) — runtime internals, startup sequence, component wiring
- [FAQ](faq.md) — why not Temporal, why not LangGraph, GIL concerns, common objections

### Contributing

- [Contributing Guide](../CONTRIBUTING.md) — dev setup, test strategy, plugin authoring

---

## Examples

All examples in the repo are independently runnable:

```bash
python examples/hello_agent.py           # simplest possible agent
python examples/supervised_agent.py      # crash + auto-restart
python examples/research_pipeline.py     # three-agent pipeline
python examples/research_assistant.py    # four-agent hero demo (no API key needed)
```

---

## License

Apache 2.0
