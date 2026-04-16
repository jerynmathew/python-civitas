# AGENTS.md

**Package:** `python-civitas` | **Import:** `import civitas` | **Python:** ≥ 3.12

This file guides AI coding agents (Claude Code, Cursor, Codex, Gemini CLI) working on
this codebase. Read it fully before writing any code.

---

## Project Overview

`python-civitas` is an OSS Python **SDK + library + CLI** for building multi-agent
systems. It exposes three distinct surfaces — keep all three in mind at all times:

- **Public SDK / library** — importable by downstream projects (`import civitas`)
- **CLI** — entry point for end users
- **Async runtime** — event-loop-based message bus, supervision tree, LLM integration

This project is meant to be adopted by the community. Code must be **simple, easy
to read, and easy to reason about**. Follow SOLID principles and established design
patterns. When in doubt, choose clarity over cleverness.

A change to an internal module can break the public SDK, the CLI, or both.

---

## Install

```bash
pip install civitas                          # core runtime (print-based console tracing)
pip install civitas[otel]                    # + OpenTelemetry tracing (Jaeger, Grafana, etc.)
pip install civitas[anthropic]               # + Anthropic Claude (native SDK)
pip install civitas[openai]                  # + OpenAI GPT-4o / o-series (native SDK)
pip install civitas[gemini]                  # + Google Gemini 2.0 / 1.5 (native SDK)
pip install civitas[mistral]                 # + Mistral Large / Codestral (native SDK)
pip install civitas[litellm]                 # + 100+ models via LiteLLM proxy
pip install civitas[anthropic,otel]          # typical dev setup
```

---

## Quick Import Reference

```python
from civitas import AgentProcess, Supervisor, Runtime, Worker
from civitas.messages import Message
from civitas.errors import CivitasError, ErrorAction
from civitas.plugins.anthropic import AnthropicProvider   # requires [anthropic]
from civitas.plugins.openai import OpenAIProvider         # requires [openai]
from civitas.plugins.gemini import GeminiProvider         # requires [gemini]
from civitas.plugins.mistral import MistralProvider       # requires [mistral]
from civitas.plugins.litellm import LiteLLMProvider       # requires [litellm]
from civitas.plugins.tools import ToolProvider, ToolRegistry
from civitas.adapters.langgraph import LangGraphAgent
from civitas.adapters.openai import OpenAIAgent
```

---

## Repository Layout

```
civitas/
  __init__.py            # Public SDK surface — be conservative here
  __main__.py            # Entry point: python -m civitas
  process.py             # AgentProcess
  supervisor.py          # Supervisor, RestartStrategy, BackoffPolicy
  runtime.py             # Runtime — wires components, manages lifecycle
  bus.py                 # MessageBus
  messages.py            # Message dataclass
  registry.py            # Registry — agent name → instance lookup
  serializer.py          # Serializer protocol + msgpack/json impls
  errors.py              # CivitasError hierarchy + ErrorAction enum
  config.py              # Settings — centralised env var access
  worker.py              # Worker — hosts agents in a worker process
  cli/                   # CLI package (see docs/08-CLI-Design.md)
    __init__.py           # App assembly, exports main()
    app.py                # Shared Typer app, Console, output helpers
    init.py               # civitas init
    run.py                # civitas run
    state.py              # civitas state list|clear
    topology.py           # civitas topology validate|show|diff
    deploy.py             # civitas deploy (M2.7)
    version.py            # civitas version
    _templates/           # Scaffolding templates ($variable syntax)
  dashboard/
    __init__.py
    collector.py          # MetricsCollector — in-memory metrics for TUI
    renderer.py           # Rich-based dashboard renderer
  transport/
    __init__.py           # Transport protocol
    inprocess.py          # InProcessTransport (default)
    zmq.py                # ZMQTransport (requires [zmq])
    nats.py               # NATSTransport (requires [nats])
  plugins/
    __init__.py
    loader.py             # Plugin discovery and instantiation
    model.py              # ModelProvider protocol + ModelResponse
    tools.py              # ToolProvider protocol + ToolRegistry
    state.py              # StateStore protocol + InMemoryStateStore
    sqlite_store.py       # SQLiteStateStore (crash recovery)
    anthropic.py          # AnthropicProvider (requires [anthropic])
    litellm.py            # LiteLLMProvider (requires [litellm])
    otel.py               # OTELExporter (requires [otel])
  observability/
    __init__.py
    tracer.py             # Tracer — OTEL span creation, context propagation
  adapters/
    __init__.py
    langgraph.py          # LangGraphAgent — wraps CompiledGraph
    openai.py             # OpenAIAgent — wraps OpenAI Agents SDK
    crewai.py             # CrewAI adapter (stub)
tests/
  unit/
  integration/             # May require API keys or external services
examples/
pyproject.toml
AGENTS.md
```

> This layout is authoritative. Keep it in sync with the actual directory structure.

---

## Environment Setup

This project uses **`uv`** for dependency management.

```bash
# Install uv if not present
curl -Ls https://astral.sh/uv/install.sh | sh

# Install all deps including dev extras
uv sync --all-extras

# Activate
source .venv/bin/activate
```

Never use bare `pip install` — always go through `uv` or edit `pyproject.toml`
and re-run `uv sync`.

### Environment variables

Set the following in your shell or a `.env` file. Never commit `.env`
or real API keys.

| Variable | Purpose | Default |
|---|---|---|
| `AGENCY_SERIALIZER` | `json` for human-readable debug output | `msgpack` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTEL collector endpoint (e.g. Jaeger) | console output |
| `ANTHROPIC_API_KEY` | Anthropic model provider (`[anthropic]`) | — |
| `OPENAI_API_KEY` | OpenAI model provider (`[openai]` or `[litellm]`) | — |
| `GEMINI_API_KEY` | Google Gemini model provider (`[gemini]` or `[litellm]`) | — |
| `MISTRAL_API_KEY` | Mistral model provider (`[mistral]`) | — |
| `FIDDLER_API_KEY` | Fiddler exporter plugin | — |
| `NATS_URL` | NATS server for distributed transport | `nats://localhost:4222` |

---

## Commands Reference

| Task | Command |
|---|---|
| Run all tests | `uv run pytest` |
| Run unit tests only | `uv run pytest tests/unit` |
| Run integration tests | `uv run pytest tests/integration/` |
| Run a single test | `uv run pytest tests/unit/test_foo.py::test_bar -v` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type-check | `uv run mypy civitas/` |
| Run CLI locally | `uv run civitas [args]` |
| Build package | `uv build` |

Run **lint + format + unit tests** before finishing any task:

```bash
uv run ruff check . && uv run ruff format . && uv run pytest tests/unit
```

---

## Core API — AgentProcess

`AgentProcess` is **always subclassed**, never instantiated directly.

```python
class MyAgent(AgentProcess):

    async def on_start(self) -> None:
        # Called once before the first message.
        # DO NOT call self.send() / self.ask() here — MessageBus is not ready.
        # Initialise persistent state here, not instance variables.
        self.state.setdefault("count", 0)

    async def handle(self, message: Message) -> Message | None:
        # Called for every incoming message.
        # All I/O must be async/await — never block here.
        # Return self.reply(...) when the caller uses ask(). Missing it hangs the caller.
        self.state["count"] += 1
        return self.reply({"count": self.state["count"]})

    async def on_error(self, error: Exception, message: Message) -> ErrorAction:
        # Default if not overridden: ErrorAction.ESCALATE
        if isinstance(error, SomeTransientError):
            return ErrorAction.RETRY
        return ErrorAction.ESCALATE

    async def on_stop(self) -> None:
        # Called on graceful shutdown.
        pass
```

**Lifecycle order:** `on_start()` → `handle()` loop → `on_error()` on exception → `on_stop()`

### Messaging methods (call from inside hooks only)

```python
await self.send("agent_name", {"type": "event", "key": "value"})        # fire-and-forget
result = await self.ask("agent_name", {"type": "query"}, timeout=30.0)  # request-reply
await self.broadcast("tool_agents.*", {"type": "cancel"})               # pattern send
return self.reply({"result": "..."})                                     # respond from handle()
```

### Injected attributes

```python
self.llm      # ModelProvider  — self.llm.chat(model, messages, tools)
self.tools    # ToolRegistry   — self.tools.get("tool_name")
self.store    # StateStore     — raw key/value store; self.store.get/set/delete(agent_name)
self.state    # dict           — in-memory dict, auto-restored from StateStore on restart
self.name     # str            — this agent's Registry name
```

**`self.state` vs `self.store`** — use `self.state` for everything in normal code:

```python
async def on_start(self) -> None:
    self.state.setdefault("counter", 0)    # ✅ initialise with a default

async def handle(self, message: Message) -> Message | None:
    self.state["counter"] += 1             # ✅ mutate in-place
    await self.checkpoint()                # ✅ persist — survives supervisor restart
    # ...
```

`self.store` is the raw `StateStore`. Use it only for advanced cases (e.g. reading
another agent's state, or wiping state for a specific agent name):

```python
await self.store.delete("other_agent")    # clear another agent's persisted state
saved = await self.store.get(self.name)   # read raw checkpoint dict
```

`self.checkpoint()` is a helper that calls `self.store.set(self.name, self.state)`.
Call it after completing a meaningful unit of work — agents that never call it
incur zero overhead.

### ErrorAction values

| Value | Behaviour |
|---|---|
| `ErrorAction.RETRY` | Re-deliver the same message (up to retry limit) |
| `ErrorAction.SKIP` | Discard message, continue with next |
| `ErrorAction.ESCALATE` | Crash process — supervisor applies restart strategy |
| `ErrorAction.STOP` | Graceful shutdown of this process |

---

## Core API — Message Schema

```python
message.id              # str        — UUID7
message.type            # str        — app-defined, e.g. "research_query"
message.sender          # str        — sending agent name
message.recipient       # str        — target agent name
message.payload         # dict       — MUST be JSON-serializable primitives only
message.correlation_id  # str | None — set by ask(); links request to reply
message.reply_to        # str | None — where to send the reply
message.timestamp       # float      — unix epoch
message.trace_id        # str        — OTEL trace ID
message.span_id         # str        — OTEL span ID
message.parent_span_id  # str | None
message.attempt         # int        — 0 = first delivery, incremented on retry
message.ttl             # float | None — expiry in seconds
message.priority        # int        — 0 = normal, 1 = high (system only)
```

**`payload` rule:** only `str`, `int`, `float`, `bool`, `list`, `dict`, `None`.
No Python objects, Pydantic models, or dataclasses — call `.model_dump()` first.

---

## Core API — Supervisor

```python
Supervisor(
    name="root",
    children=[AgentA("a"), AgentB("b"), Supervisor("child_sup", children=[...])],
    strategy="ONE_FOR_ONE",    # "ONE_FOR_ONE" | "ONE_FOR_ALL" | "REST_FOR_ONE"
    max_restarts=3,
    restart_window=60.0,       # seconds
    backoff="EXPONENTIAL",     # "CONSTANT" | "LINEAR" | "EXPONENTIAL"
)
```

**Strategy guide:**
- `ONE_FOR_ONE` — children are independent. One crash restarts only that child. *(most common)*
- `ONE_FOR_ALL` — children are interdependent. One crash restarts all siblings.
- `REST_FOR_ONE` — children form a pipeline. One crash restarts it and all downstream children.

---

## Core API — Runtime

```python
# Code-first
runtime = Runtime(
    supervisor=Supervisor("root", children=[MyAgent("my_agent")])
)

# Config-first
runtime = Runtime.from_config("topology.yaml")

# Lifecycle
await runtime.start()
result = await runtime.ask("agent_name", {"type": "...", "key": "value"}, timeout=30.0)
await runtime.send("agent_name", {"type": "..."})
await runtime.stop()
```

`asyncio.run()` is valid **only** in CLI entry points and test helpers.
Never call it inside `AgentProcess` subclasses or library code.

---

## Core API — Topology YAML

```yaml
transport:
  type: in_process          # in_process | zmq | nats

plugins:
  models:
    - type: anthropic        # short name; or full dotted path
      config:
        default_model: claude-sonnet-4-6
  exporters:
    - type: console          # or: otel
  state:
    type: sqlite
    config:
      db_path: /data/civitas.db

supervision:
  name: root
  strategy: ONE_FOR_ONE
  max_restarts: 3
  restart_window: 60
  children:
    - agent:
        name: research
        type: myapp.agents.ResearchAgent
    - agent:
        name: summarizer
        type: myapp.agents.SummarizerAgent
```

---

## Core API — Tools

Tools are implemented as classes that satisfy the `ToolProvider` protocol and
registered in a `ToolRegistry` that is passed to `Runtime`.

### Defining a tool

```python
from typing import Any
from civitas.plugins.tools import ToolProvider, ToolRegistry

class WebSearchTool:
    """Search the web and return a list of results."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": "web_search",
            "description": "Search the web for a query and return results.",
            "input_schema": {           # Anthropic-style JSON Schema
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"],
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        query = kwargs["query"]
        # ... perform the search ...
        return {"results": [...]}
```

> The `schema` dict must conform to the tool format expected by your model provider.
> Anthropic uses `input_schema`; OpenAI uses `parameters`. If you use multiple
> providers, keep schemas per-provider or use LiteLLM (which normalises them).

### Registering tools and wiring to Runtime

```python
registry = ToolRegistry()
registry.register(WebSearchTool())
registry.register(CalculatorTool())

runtime = Runtime(
    supervisor=Supervisor("root", children=[ResearchAgent("researcher")]),
    model_provider=AnthropicProvider(),
    tool_registry=registry,
)
```

### Using tools inside `handle()`

`self.llm.chat()` returns a `ModelResponse`. When the model wants to call a tool,
`response.tool_calls` is a non-empty list of `ToolCall` objects. Execute them and
send the results back to the model in a second call.

```python
async def handle(self, message: Message) -> Message | None:
    messages = [{"role": "user", "content": message.payload["query"]}]

    # First call — model may request tool use
    response = await self.llm.chat(
        model="claude-sonnet-4-6",
        messages=messages,
        tools=[t.schema for t in self.tools.list_tools()],
    )

    # Tool-call loop
    while response.tool_calls:
        tool_results = []
        for tc in response.tool_calls:
            tool = self.tools.get(tc.name)
            if tool is None:
                raise ValueError(f"Unknown tool: {tc.name}")
            result = await tool.execute(**tc.input)
            tool_results.append({"tool_use_id": tc.id, "content": str(result)})

        # Append assistant turn + tool results, then call the model again
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
        response = await self.llm.chat(
            model="claude-sonnet-4-6",
            messages=messages,
            tools=[t.schema for t in self.tools.list_tools()],
        )

    return self.reply({"answer": response.content})
```

**Rules:**
- Always check `self.tools is not None` before use — the registry is only injected
  when `tool_registry=` is passed to `Runtime`.
- `ToolCall` fields: `tc.id` (str), `tc.name` (str), `tc.input` (dict).
- Tool results must be plain JSON-serializable values.
- Do not call `tool.execute()` from `on_start()` — the bus is not ready.

---

## LLM Calls

All LLM calls go through `self.llm.chat()` — never call provider SDKs directly
from `AgentProcess`. Provider specifics are configured in topology; call sites
are identical across providers.

All providers share the same call signature. Select the provider via `Runtime(model_provider=...)`.

```python
# Anthropic (requires [anthropic] extra)
runtime = Runtime(supervisor=..., model_provider=AnthropicProvider())
# inside handle():
response = await self.llm.chat(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": message.payload["query"]}],
    tools=[t.schema for t in self.tools.list_tools()],   # optional
)

# OpenAI (requires [openai] extra)
runtime = Runtime(supervisor=..., model_provider=OpenAIProvider())
response = await self.llm.chat(model="gpt-4o", messages=[...])

# Gemini (requires [gemini] extra)
runtime = Runtime(supervisor=..., model_provider=GeminiProvider())
response = await self.llm.chat(model="gemini-2.0-flash", messages=[...])

# Mistral (requires [mistral] extra)
runtime = Runtime(supervisor=..., model_provider=MistralProvider())
response = await self.llm.chat(model="mistral-large-latest", messages=[...])

# LiteLLM — 100+ models via one interface (requires [litellm] extra)
runtime = Runtime(supervisor=..., model_provider=LiteLLMProvider())
response = await self.llm.chat(model="gemini/gemini-2.0-flash", messages=[...])
```

`ModelResponse` fields:

| Field | Type | Notes |
|---|---|---|
| `response.content` | `str` | Final text from the model |
| `response.model` | `str` | Model name echoed by the provider |
| `response.tokens_in` | `int` | Prompt tokens |
| `response.tokens_out` | `int` | Completion tokens |
| `response.cost_usd` | `float \| None` | Computed from hardcoded pricing table; `None` if model unknown |
| `response.tool_calls` | `list[ToolCall] \| None` | Non-empty when the model requests tool use |

**Rules:**
- All LLM calls must be `async` — `self.llm.chat()` is already async.
- Prefer named constants for model names when available; inline strings are
  acceptable until `civitas.models` is introduced.
- Mock `self.llm` in unit tests — never make real API calls in `tests/unit/`.
- `429` / transient error handling is built into the provider layer. Do not add
  a second retry layer on top unless explicitly required.

### Observability helpers

Wrap LLM and tool calls in spans for tracing (no-ops when no tracer is configured):

```python
async def handle(self, message: Message) -> Message | None:
    with self.llm_span("claude-sonnet-4-6") as span:
        response = await self.llm.chat(model="claude-sonnet-4-6", messages=[...])
        span.set_attribute("civitas.llm.tokens_out", response.tokens_out)

    with self.tool_span("web_search") as span:
        result = await self.tools.get("web_search").execute(query="...")
        span.set_attribute("civitas.tool.result_size_bytes", len(str(result)))
```

---

## Multi-Agent Pattern

```python
class OrchestratorAgent(AgentProcess):
    async def handle(self, message: Message):
        # Prefer TaskGroup over asyncio.gather for structured concurrency
        async with asyncio.TaskGroup() as tg:
            ta = tg.create_task(
                self.ask("worker_a", {"type": "process", "chunk": message.payload["a"]})
            )
            tb = tg.create_task(
                self.ask("worker_b", {"type": "process", "chunk": message.payload["b"]})
            )
        combined = [ta.result().payload["result"], tb.result().payload["result"]]
        summary = await self.ask("summarizer", {"type": "summarize", "items": combined})
        return self.reply(summary.payload)

async def main():
    runtime = Runtime(
        supervisor=Supervisor("root", strategy="ONE_FOR_ONE", children=[
            OrchestratorAgent("orchestrator"),
            WorkerA("worker_a"),
            WorkerB("worker_b"),
            SummarizerAgent("summarizer"),
        ])
    )
    await runtime.start()
    result = await runtime.ask("orchestrator", {"type": "run", "a": [...], "b": [...]})
    await runtime.stop()

asyncio.run(main())
```

---

## Code Style

- **Formatter / linter:** `ruff` (format + lint). Config in `pyproject.toml`.
  Do not introduce `black` or `flake8` — `ruff` covers both.
- **Line length:** 100 (configured in `pyproject.toml`).
- **Imports:** top-level only, sorted by `ruff` (`I` rules). See anti-patterns below.
- **Type hints:** required on all public functions and method signatures.
  Use `from __future__ import annotations` at the top of every module.
- **Docstrings:** Google style. Required on all public classes and functions.
- **Private symbols:** prefix with `_`. Anything without `_` is considered public API.

---

## Async Conventions

- All I/O-bound operations **must be async** (`async def` + `await`).
- Never use `time.sleep()` — always `await asyncio.sleep()`.
- Never call `asyncio.run()` inside `AgentProcess` or library code.
- Use `asyncio.TaskGroup` (Python ≥ 3.11) for concurrent tasks; prefer it over
  bare `asyncio.gather`.
- Do not use `threading` for I/O. If blocking calls are unavoidable, wrap with
  `asyncio.to_thread`.
- Always use `async with` for async clients and resources — never leave them open.
- Tests for async code use `pytest-asyncio`. Mark them `@pytest.mark.asyncio`.

---

## Testing

- **Unit tests** (`tests/unit/`): no network, no API keys, fast. Mock `self.llm`,
  `self.store`, and all HTTP clients.
- **Integration tests** (`tests/integration/`): may call real APIs. Skipped by default in CI.
  Run locally: `uv run pytest tests/integration/`
- Aim for **≥ 85% coverage** (enforced by `--cov-fail-under` in pyproject.toml).
- Test file names mirror source: `civitas/bus.py` → `tests/unit/test_bus.py`.
- Use `pytest.fixture` over `setUp`/`tearDown`. Prefer function-scoped fixtures.

---

## Public SDK & CLI Stability

- `civitas/__init__.py` is the **public surface**. Think twice before removing
  or renaming anything exported there — it is a breaking change.
- CLI argument names and output formats are also public API. Changing them requires
  a deprecation notice in the changelog.
- Add a `# BREAKING CHANGE:` comment on any line that removes or renames a public
  symbol so reviewers catch it immediately.
- Follow **semver**: patch for fixes, minor for new features, major for breaking changes.

---

## Agent Anti-Patterns — Read This Carefully

These are mistakes AI coding agents make frequently. Every item here represents
a real class of bug. Do not do any of these.

---

### 1. Scoped imports

**Never** place `import` statements inside functions, methods, or `if` blocks,
even to resolve circular imports. All imports belong at the top of the file.
Fix circular imports by refactoring — not by scoping.

**Two exceptions:**

1. **`TYPE_CHECKING` guards** — standard practice for breaking circular import
   cycles without runtime cost. These are endorsed by PEP 484, mypy, and pyright.
   ```python
   from __future__ import annotations
   from typing import TYPE_CHECKING

   if TYPE_CHECKING:
       from civitas.bus import MessageBus
   ```

2. **Optional dependency gating** — imports of packages from optional extras
   (`[anthropic]`, `[otel]`, `[zmq]`, `[nats]`) must be guarded so that
   `import civitas` does not fail when the extra is not installed.
   ```python
   # ✅ Acceptable — nats-py is an optional extra
   if self._transport_type == "nats":
       from civitas.transport.nats import NATSTransport
   ```

Outside these two cases, all imports belong at the top of the file.

```python
# ❌ Wrong — yaml is a core dependency, no reason to scope
def load_config():
    import yaml
    return yaml.safe_load(...)

# ✅ Correct
import yaml

def load_config():
    return yaml.safe_load(...)
```

---

### 2. Missing `self.reply()` in a request-reply handler

If a caller uses `ask()`, the handler **must** `return self.reply(...)`.
Omitting it causes the caller to hang silently until timeout.

```python
# ❌ Wrong — ask() will hang until timeout
async def handle(self, message: Message) -> Message | None:
    result = await self.llm.chat(...)
    # no return

# ✅ Correct
async def handle(self, message: Message) -> Message | None:
    result = await self.llm.chat(...)
    return self.reply({"result": result.content})
```

---

### 3. Non-serializable payload

`payload` must contain only JSON-serializable primitives. Pydantic models,
dataclasses, or any Python object will fail at the serialization boundary.

```python
# ❌ Wrong
await self.send("next", {"data": my_pydantic_model})

# ✅ Correct
await self.send("next", {"data": my_pydantic_model.model_dump()})
```

---

### 4. Sending messages from `on_start()`

The MessageBus is not ready during `on_start()`. Any call to `self.send()` or
`self.ask()` there will fail. Send the first outbound message from `handle()`.

```python
# ❌ Wrong
async def on_start(self):
    await self.send("other_agent", {"type": "init"})   # MessageBus not ready

# ✅ Correct
async def handle(self, message: Message):
    if message.type == "start":
        await self.send("other_agent", {"type": "init"})
```

---

### 5. Instance variables for persistent state

Instance variables reset when a supervisor restarts the process. State that must
survive restarts goes in `self.state`, which is persisted to `StateStore`.

```python
# ❌ Wrong — resets to 0 on every supervisor restart
def __init__(self, name):
    super().__init__(name)
    self.counter = 0

# ✅ Correct
async def on_start(self):
    self.state.setdefault("counter", 0)
```

---

### 6. Calling agent methods directly

Direct object references bypass the message bus, supervision, and distributed
tracing. Always route to agents by name.

```python
# ❌ Wrong — bypasses supervision and tracing
await some_agent_ref.handle(message)

# ✅ Correct
await self.send("summarizer", {"type": "summarize", "text": text})
```

---

### 7. Using the `_agency.` message type prefix

Names starting with `_agency.` are reserved for runtime internals.

```python
# ❌ Wrong
await self.send("other", {"type": "_agency.custom"})

# ✅ Correct
await self.send("other", {"type": "myapp.custom_event"})
```

---

### 8. Blocking I/O inside `handle()`

`handle()` runs on the event loop. Blocking calls stall all agents sharing
that loop. Use async HTTP clients for all network I/O.

```python
# ❌ Wrong — blocks the event loop
result = requests.get("https://api.example.com")

# ✅ Correct
async with aiohttp.ClientSession() as session:
    async with session.get("https://api.example.com") as resp:
        result = await resp.json()
```

---

### 9. `assert` for runtime validation

`assert` is stripped when Python runs with `-O`. Never use it for real validation.

```python
# ❌ Wrong
assert api_key, "API key required"

# ✅ Correct
if not api_key:
    raise ValueError("API key required")
```

---

### 10. `# type: ignore` as a crutch

Fix the underlying type issue. If suppression is genuinely unavoidable, use a
specific error code and an explanatory comment:
`# type: ignore[assignment]  # upstream library returns Any`

---

### 11. `time.sleep` in async code

```python
# ❌ Wrong — blocks the event loop
time.sleep(1)

# ✅ Correct
await asyncio.sleep(1)
```

---

### 12. Module-level side effects

Never instantiate clients, open files, or make network calls at module level.
They run at import time, slow down imports, and break testability.

```python
# ❌ Wrong — runs at import time
client = Anthropic()

# ✅ Correct
def get_client() -> Anthropic:
    return Anthropic()
```

---

### 13. Broad or silent exception handling

- Never use bare `except:` — catches `KeyboardInterrupt` and `SystemExit`.
- Never use `except Exception:` without re-raising or converting to a domain exception.
- All project exceptions live in `civitas/errors.py` and inherit from `CivitasError`.

```python
# ❌ Wrong
try:
    ...
except:
    pass

# ✅ Correct
try:
    ...
except SomeSpecificError as e:
    raise CivitasError("Context about what failed") from e
```

---

### 14. String path concatenation

```python
# ❌ Wrong
path = base_dir + "/config/" + filename

# ✅ Correct
path = Path(base_dir) / "config" / filename
```

---

### 15. f-strings in logging calls

f-strings evaluate eagerly even when the log level suppresses the message.

```python
# ❌ Wrong
logger.debug(f"Processing {len(items)} items for user {user_id}")

# ✅ Correct
logger.debug("Processing %d items for user %s", len(items), user_id)
```

---

### 16. Mutable default arguments

```python
# ❌ Wrong — the list is shared across all calls
def process(items: list = []):
    ...

# ✅ Correct
def process(items: list | None = None):
    if items is None:
        items = []
```

---

### 17. Not closing async resources

Async clients, sessions, and connections must be used as context managers.

```python
# ❌ Wrong — leaks the connection
client = AsyncClient()
response = await client.get(url)

# ✅ Correct
async with AsyncClient() as client:
    response = await client.get(url)
```

---

### 18. Reading env vars directly

Never call `os.environ["KEY"]` in application code — it throws on missing keys
and scatters config logic. Use the central settings object (`civitas/config.py`).

```python
# ❌ Wrong
api_key = os.environ["ANTHROPIC_API_KEY"]

# ✅ Correct
from civitas.config import settings
api_key = settings.anthropic_api_key
```

> `civitas.config` is implemented. All env var reads must go through `settings`.

---

## What NOT to Do

- ❌ Don't add new top-level dependencies without discussion — keep the install
  footprint small for a library meant for wide adoption.
- ❌ Don't use `print()` in library or SDK code — use the `logging` module.
- ❌ Don't suppress `ruff` warnings with `# noqa` without an explanatory comment.
- ❌ Don't hardcode model name strings when constants are available.
- ❌ Don't call provider SDKs (Anthropic, OpenAI, etc.) directly from `AgentProcess`
  — always go through `self.llm`.
- ❌ Don't commit code that fails `ruff check` or `pytest tests/unit`.
- ❌ Don't let `__all__` in `__init__.py` fall out of sync with the public surface.

---

## Pull Request Checklist

- [ ] `uv run ruff check .` passes with no errors
- [ ] `uv run ruff format .` produces no diff
- [ ] `uv run pytest tests/unit` passes
- [ ] Type hints on all new public functions
- [ ] Google-style docstrings on all new public classes / functions
- [ ] `CHANGELOG.md` updated (if user-visible change)
- [ ] No secrets, `.env` files, or real API keys committed
- [ ] `__all__` in `__init__.py` updated if the public surface changed

---

## Changelog

Maintain `CHANGELOG.md` using [Keep a Changelog](https://keepachangelog.com/)
format. Add entries under `[Unreleased]` as you work; don't wait for release.
