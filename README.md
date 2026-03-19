# Agency

**The production runtime for Python agents.**

Agency is an OTP-inspired agent runtime that provides supervision trees, message passing, and automatic observability for Python agent systems. Build agents that crash safely, restart automatically, and trace every decision.

## Quick Start

```bash
pip install python-agency
```

```python
import asyncio
from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message

class Greeter(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        name = message.payload.get("name", "world")
        return self.reply({"greeting": f"Hello, {name}!"})

async def main():
    runtime = Runtime(
        supervisor=Supervisor("root", children=[Greeter("greeter")])
    )
    await runtime.start()
    result = await runtime.ask("greeter", {"name": "Agency"})
    print(result.payload["greeting"])  # Hello, Agency!
    await runtime.stop()

asyncio.run(main())
```

**Time to run: under 2 minutes from `pip install`.**

## Features

- **Supervision trees** — agents crash safely and restart automatically with configurable strategies (ONE_FOR_ONE, ONE_FOR_ALL, REST_FOR_ONE)
- **Message passing** — `send` (fire-and-forget), `ask` (request-reply), `broadcast` (pattern-matched)
- **Backpressure** — bounded mailboxes prevent runaway producers
- **LLM integration** — `ModelProvider` protocol with first-party Anthropic support
- **Tool system** — `ToolProvider` protocol with schema-based registration
- **Automatic observability** — every message, LLM call, and tool invocation generates OTEL spans
- **YAML topologies** — define supervision trees in YAML or Python DSL
- **Zero framework deps** — no LangChain, no CrewAI, just Agency

## Examples

```bash
python examples/hello_agent.py           # M1.1 — basic agent
python examples/supervised_agent.py      # M1.2 — crash recovery
python examples/research_pipeline.py     # M1.3 — multi-agent pipeline
python examples/self_sufficient_agent.py # M1.4 — LLM + tools
python examples/observable_pipeline.py   # M1.5 — traced spans
python examples/supervision_tree.py      # M1.6 — YAML topology
python examples/research_assistant.py    # M1.7 — hero demo (4 agents, full trace)
```

## Hero Demo

```bash
# No API key needed — uses mock LLM
python examples/research_assistant.py "Compare AI safety approaches"

# With real LLM
export ANTHROPIC_API_KEY=...
python examples/research_assistant.py "Compare AI safety approaches" --live

# With Jaeger tracing
docker run -d -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
python examples/research_assistant.py "Compare AI safety approaches"
```

## Requirements

- Python 3.11+
- Core dependencies: `msgpack`, `pyyaml`
- Optional: `opentelemetry-sdk` (OTEL tracing), `anthropic` (Anthropic LLM provider)

## License

Apache 2.0
