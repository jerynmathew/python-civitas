"""Pattern: Content Router.

A Router agent inspects each incoming message and forwards it to the
appropriate specialist agent based on content. The router never does the
work itself — it dispatches and returns the specialist's reply.

Use this when:
  - Multiple specialists handle different message types
  - You want to add/remove specialists without touching caller code
  - Routing logic may evolve independently of handler logic

Specialists: CodeAgent, DataAgent, GeneralAgent

Run:
    uv run python examples/patterns/router.py
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message

# ---------------------------------------------------------------------------
# Specialists
# ---------------------------------------------------------------------------

CODE_KEYWORDS = {"python", "code", "function", "class", "bug", "error", "import", "async"}
DATA_KEYWORDS = {"data", "csv", "json", "sql", "database", "query", "table", "column"}


class CodeAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        q = message.payload.get("question", "")
        return self.reply({
            "answer": f"[code specialist] For '{q}': use a context manager and add type hints.",
            "specialist": "code",
        })


class DataAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        q = message.payload.get("question", "")
        return self.reply({
            "answer": f"[data specialist] For '{q}': index the join column and use EXPLAIN.",
            "specialist": "data",
        })


class GeneralAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        q = message.payload.get("question", "")
        return self.reply({
            "answer": f"[general] For '{q}': great question — here's a general answer.",
            "specialist": "general",
        })


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class Router(AgentProcess):
    """Classifies questions and forwards to the right specialist."""

    def _classify(self, question: str) -> str:
        words = set(question.lower().split())
        if words & CODE_KEYWORDS:
            return "code_agent"
        if words & DATA_KEYWORDS:
            return "data_agent"
        return "general_agent"

    async def handle(self, message: Message) -> Message | None:
        question = message.payload.get("question", "")
        destination = self._classify(question)
        print(f"  [router] '{question[:40]}...' → {destination}")
        reply = await self.ask(destination, message.payload)
        return self.reply(reply.payload)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            children=[
                Router("router"),
                CodeAgent("code_agent"),
                DataAgent("data_agent"),
                GeneralAgent("general_agent"),
            ],
        )
    )
    await runtime.start()

    questions = [
        "How do I write an async function in Python?",
        "Why is my SQL query slow on a large table?",
        "What is the actor model?",
        "How do I fix this import error?",
        "Best way to store JSON data in a database?",
    ]

    print("Routing questions to specialists:\n")
    for question in questions:
        reply = await runtime.ask("router", {"question": question})
        print(f"  Q: {question}")
        print(f"  A: {reply.payload['answer']}")
        print()

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
