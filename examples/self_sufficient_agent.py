"""M1.4 — LLM + Tools: An agent that uses an LLM and a tool.

Demonstrates ModelProvider and ToolProvider plugin injection via Runtime.
"""

import asyncio
from typing import Any

from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message
from agency.plugins.anthropic import AnthropicProvider
from agency.plugins.tools import ToolRegistry


class WebSearchTool:
    """Simple tool that simulates a web search."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": "web_search",
            "description": "Search the web for information",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        query = kwargs.get("query", "")
        return {"results": [f"Result for: {query}"]}


class SmartAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        question = message.payload.get("question", "")

        # Use LLM
        response = await self.llm.chat(
            model=None,
            messages=[{"role": "user", "content": question}],
        )

        # Use tool
        search_tool = self.tools.get("web_search")
        if search_tool:
            search_results = await search_tool.execute(query=question)
        else:
            search_results = None

        return self.reply(
            {
                "answer": response.content,
                "search": search_results,
                "tokens": response.tokens_in + response.tokens_out,
            }
        )


async def main():
    tools = ToolRegistry()
    tools.register(WebSearchTool())

    runtime = Runtime(
        supervisor=Supervisor("root", children=[SmartAgent("smart")]),
        model_provider=AnthropicProvider(),
        tool_registry=tools,
    )
    await runtime.start()
    result = await runtime.ask("smart", {"question": "What is Agency?"})
    print(f"Answer: {result.payload['answer'][:200]}")
    print(f"Tokens used: {result.payload['tokens']}")
    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
