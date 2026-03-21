"""M1.7 — Phase 1 Hero Demo: Research Assistant.

A four-agent supervised pipeline that researches a topic, synthesizes findings,
and produces a structured report. Demonstrates supervision, multi-agent
communication, LLM calls, tool usage, observability, and failure recovery.

Usage:
    python examples/research_assistant.py "Compare AI safety approaches"
    python examples/research_assistant.py "Compare AI safety approaches" --live

With Jaeger:
    docker run -d -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
    python examples/research_assistant.py "Compare AI safety approaches"
"""

import asyncio
import random
import sys
from typing import Any

from agency import AgentProcess, Runtime, Supervisor
from agency.errors import ErrorAction
from agency.messages import Message
from agency.plugins.model import ModelResponse
from agency.plugins.tools import ToolRegistry

# -- Mock providers (zero deps, no API key) --

MOCK_RESPONSES = {
    "plan": "Research plan:\n1. Survey recent publications\n2. Compare approaches\n3. Identify consensus\n4. Assess implications",
    "synthesis": "Key findings:\n- Multiple approaches with different trade-offs\n- Consensus emerging on core principles\n- Practical implementation varies\n- Active area with rapid development",
    "report": "# Research Report\n\n## Overview\nThis report examines the topic from multiple angles.\n\n## Findings\nSeveral key themes emerged across sources.\n\n## Conclusion\nThe field shows significant activity with converging approaches.",
}


class MockLLM:
    async def chat(self, model=None, messages=None, tools=None) -> ModelResponse:
        content = (messages or [{}])[-1].get("content", "").lower()
        for key, text in MOCK_RESPONSES.items():
            if key in content or ("combin" in content and key == "synthesis"):
                break
        else:
            text = f"Analysis of: {content[:100]}"
        return ModelResponse(
            content=text, model=model or "mock-claude",
            tokens_in=len(content.split()) * 2, tokens_out=len(text.split()) * 2,
            cost_usd=round(random.uniform(0.001, 0.01), 4),
        )


class WebSearchTool:
    def __init__(self) -> None:
        self._calls = 0

    name = "web_search"
    schema: dict[str, Any] = {
        "name": "web_search", "description": "Search the web",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }

    async def execute(self, **kwargs: Any) -> Any:
        self._calls += 1
        query = kwargs.get("query", "")
        if self._calls == 2:  # simulate transient failure
            raise ConnectionError(f"Search temporarily unavailable for: {query}")
        return {"results": [f"[Source {self._calls}] Findings on: {query}"]}


# -- Agents --

class Orchestrator(AgentProcess):
    """Plans research and fans out tasks to WebResearchers."""

    async def handle(self, message: Message) -> Message | None:
        query = message.payload.get("query", "")
        tracer = self._tracer

        # Plan with LLM
        span = tracer.start_llm_span("mock-claude", trace_id=message.trace_id)
        plan = await self.llm.chat(messages=[{"role": "user", "content": f"Plan research on: {query}"}])
        tracer.end_llm_span(span, tokens_in=plan.tokens_in, tokens_out=plan.tokens_out, cost_usd=plan.cost_usd)

        # Fan out to researcher
        findings = []
        for i in range(3):
            r = await self.ask("web_researcher", {"query": f"{query} — aspect {i + 1}"})
            findings.append(r.payload.get("finding", ""))

        # Synthesize → Write
        synthesis = await self.ask("synthesizer", {"findings": findings, "query": query})
        report = await self.ask("writer", {"synthesis": synthesis.payload, "query": query})
        return self.reply({"report": report.payload.get("report", ""), "query": query})


class WebResearcher(AgentProcess):
    """Searches the web; retries on transient failures."""

    async def on_error(self, error: Exception, message: Message) -> ErrorAction:
        if isinstance(error, ConnectionError) and message.attempt < 2:
            print(f"  [retry] {self.name}: {error} (attempt {message.attempt + 1})")
            return ErrorAction.RETRY
        return ErrorAction.ESCALATE

    async def handle(self, message: Message) -> Message | None:
        query = message.payload.get("query", "")
        tracer = self._tracer
        tool = self.tools.get("web_search")
        span = tracer.start_tool_span("web_search", trace_id=message.trace_id)
        result = await tool.execute(query=query)
        tracer.end_tool_span(span, status="ok")
        return self.reply({"finding": str(result["results"])})


class Synthesizer(AgentProcess):
    """Combines research findings using the LLM."""

    async def handle(self, message: Message) -> Message | None:
        findings, query = message.payload.get("findings", []), message.payload.get("query", "")
        tracer = self._tracer
        span = tracer.start_llm_span("mock-claude", trace_id=message.trace_id)
        r = await self.llm.chat(messages=[{"role": "user", "content": f"Synthesize and combine on '{query}':\n" + "\n".join(findings)}])
        tracer.end_llm_span(span, tokens_in=r.tokens_in, tokens_out=r.tokens_out, cost_usd=r.cost_usd)
        return self.reply({"synthesis": r.content, "query": query})


class Writer(AgentProcess):
    """Produces the final report using the LLM."""

    async def handle(self, message: Message) -> Message | None:
        synthesis, query = message.payload.get("synthesis", {}), message.payload.get("query", "")
        tracer = self._tracer
        content = synthesis.get("synthesis", str(synthesis)) if isinstance(synthesis, dict) else str(synthesis)
        span = tracer.start_llm_span("mock-claude", trace_id=message.trace_id)
        r = await self.llm.chat(messages=[{"role": "user", "content": f"Write a report on '{query}' from:\n{content}"}])
        tracer.end_llm_span(span, tokens_in=r.tokens_in, tokens_out=r.tokens_out, cost_usd=r.cost_usd)
        return self.reply({"report": r.content})


# -- Main --

async def main() -> None:
    query = " ".join(sys.argv[1:]).replace("--live", "").strip()
    if not query:
        query = "Compare the approaches to AI safety used by Anthropic, OpenAI, and DeepMind"
    use_live = "--live" in sys.argv

    if use_live:
        from agency.plugins.anthropic import AnthropicProvider
        llm = AnthropicProvider()
    else:
        llm = MockLLM()

    tools = ToolRegistry()
    tools.register(WebSearchTool())

    runtime = Runtime(
        supervisor=Supervisor("root", strategy="ONE_FOR_ONE", max_restarts=5, children=[
            Supervisor("research_sup", strategy="ONE_FOR_ONE", max_restarts=3,
                       backoff="CONSTANT", backoff_base=0.1, children=[WebResearcher("web_researcher")]),
            Orchestrator("orchestrator"),
            Synthesizer("synthesizer"),
            Writer("writer"),
        ]),
        model_provider=llm, tool_registry=tools,
    )

    print(f"\n{'='*60}")
    print(f"  Agency Research Assistant — M1.7 Hero Demo")
    print(f"  Query: {query}")
    print(f"  LLM: {'AnthropicProvider' if use_live else 'MockLLM (no API key needed)'}")
    print(f"{'='*60}\n")
    print("=== Supervision Tree ===")
    print(runtime.print_tree())
    print()

    await runtime.start()
    result = await runtime.ask("orchestrator", {"query": query})

    print(f"\n{'='*60}")
    print("  RESEARCH REPORT")
    print(f"{'='*60}")
    print(result.payload.get("report", ""))
    print(f"{'='*60}\n")

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
