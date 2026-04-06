"""Quickstart 4: Agent with LLM.

An agent that calls an LLM to answer questions. Runs with a mock LLM by
default (no API key needed). Pass --live to use AnthropicProvider.

The mock provider has the same interface as AnthropicProvider — swap it
out by changing one line.

Run:
    uv run python examples/quickstart/04_with_llm.py
    uv run python examples/quickstart/04_with_llm.py --live   # needs ANTHROPIC_API_KEY
"""

import asyncio
import sys

from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message
from agency.plugins.model import ModelResponse


# ---------------------------------------------------------------------------
# Mock provider — same interface as AnthropicProvider, no API key needed
# ---------------------------------------------------------------------------

class MockLLM:
    async def chat(
        self,
        model: str | None = None,
        messages: list | None = None,
        tools: list | None = None,
    ) -> ModelResponse:
        question = (messages or [{}])[-1].get("content", "")
        answer = f"[mock] Here is a concise answer to: '{question[:60]}'"
        return ModelResponse(
            content=answer,
            model=model or "mock",
            tokens_in=len(question.split()),
            tokens_out=len(answer.split()),
            cost_usd=0.0,
        )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class QAAgent(AgentProcess):
    """Answers questions using the injected LLM."""

    async def handle(self, message: Message) -> Message | None:
        question = message.payload.get("question", "")

        response = await self.llm.chat(
            model="claude-sonnet-4-6",
            messages=[
                {"role": "user", "content": question},
            ],
        )

        return self.reply({
            "answer": response.content,
            "tokens": response.tokens_in + response.tokens_out,
            "cost_usd": response.cost_usd,
        })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    use_live = "--live" in sys.argv

    if use_live:
        from agency.plugins.anthropic import AnthropicProvider
        llm = AnthropicProvider()
        print("Using AnthropicProvider (live)\n")
    else:
        llm = MockLLM()
        print("Using MockLLM (no API key needed). Pass --live for real responses.\n")

    runtime = Runtime(
        supervisor=Supervisor("root", children=[QAAgent("qa")]),
        model_provider=llm,
    )
    await runtime.start()

    questions = [
        "What is the actor model?",
        "Why use supervision trees instead of try/except?",
        "When should I use NATS over ZMQ?",
    ]

    for question in questions:
        reply = await runtime.ask("qa", {"question": question})
        print(f"Q: {question}")
        print(f"A: {reply.payload['answer']}")
        print(f"   tokens={reply.payload['tokens']}  cost=${reply.payload['cost_usd']:.4f}")
        print()

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
