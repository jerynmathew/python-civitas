"""M1.5 — Automatic Observability: A pipeline with traced LLM and tool calls.

Every message send/receive, LLM call, and tool invocation generates a span.
With OTEL installed, spans export to Jaeger/Grafana; without it, a readable
console summary is printed.
"""

import asyncio
from typing import Any

from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message
from agency.plugins.model import ModelResponse
from agency.plugins.tools import ToolRegistry


# -- Mock LLM provider (replace with AnthropicProvider for real use) --
class DemoLLM:
    async def chat(self, model=None, messages=None, tools=None) -> ModelResponse:
        return ModelResponse(
            content="The capital of France is Paris.",
            model=model or "demo",
            tokens_in=15,
            tokens_out=8,
            cost_usd=0.0003,
        )


# -- Mock tool --
class FactCheckTool:
    @property
    def name(self) -> str:
        return "fact_check"

    @property
    def schema(self) -> dict[str, Any]:
        return {"name": "fact_check", "description": "Verify a claim"}

    async def execute(self, **kwargs: Any) -> Any:
        return {"verified": True, "confidence": 0.95}


class ResearchAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        # Traced LLM call
        tracer = self._tracer
        llm_span = tracer.start_llm_span("demo", trace_id=message.trace_id)
        response = await self.llm.chat(model="demo", messages=[
            {"role": "user", "content": message.payload.get("question", "")}
        ])
        tracer.end_llm_span(llm_span, tokens_in=response.tokens_in,
                            tokens_out=response.tokens_out, cost_usd=response.cost_usd)

        # Traced tool call
        tool = self.tools.get("fact_check")
        tool_span = tracer.start_tool_span("fact_check", trace_id=message.trace_id)
        result = await tool.execute(claim=response.content)
        tracer.end_tool_span(tool_span, status="ok")

        return self.reply({
            "answer": response.content,
            "verified": result["verified"],
        })


async def main():
    tools = ToolRegistry()
    tools.register(FactCheckTool())

    runtime = Runtime(
        supervisor=Supervisor("root", children=[ResearchAgent("researcher")]),
        model_provider=DemoLLM(),
        tool_registry=tools,
    )
    await runtime.start()
    result = await runtime.ask("researcher", {"question": "What is the capital of France?"})
    print(f"\nAnswer: {result.payload['answer']} (verified: {result.payload['verified']})")
    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
