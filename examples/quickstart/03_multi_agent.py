"""Quickstart 3: Multi-Agent Pipeline.

Three agents form a pipeline: Fetcher → Analyzer → Formatter.
The Coordinator drives the pipeline and returns the final result.

Demonstrates:
  - self.ask() for request-reply between agents
  - self.state for lightweight per-agent counters
  - All agents under one supervisor

Run:
    uv run python examples/quickstart/03_multi_agent.py
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message


class Fetcher(AgentProcess):
    """Simulates fetching data from a source."""

    async def handle(self, message: Message) -> Message | None:
        topic = message.payload.get("topic", "unknown")
        # Simulate fetched content
        raw = f"Raw data about '{topic}': [fact A, fact B, fact C]"
        return self.reply({"raw": raw, "topic": topic})


class Analyzer(AgentProcess):
    """Extracts key points from raw data."""

    async def handle(self, message: Message) -> Message | None:
        raw = message.payload.get("raw", "")
        points = [s.strip() for s in raw.split(",") if s.strip()]
        return self.reply({"points": points, "count": len(points)})


class Formatter(AgentProcess):
    """Formats analysis results into a report."""

    async def handle(self, message: Message) -> Message | None:
        points = message.payload.get("points", [])
        topic = message.payload.get("topic", "")
        report = f"Report on '{topic}':\n" + "\n".join(f"  • {p}" for p in points)
        return self.reply({"report": report})


class Coordinator(AgentProcess):
    """Drives the pipeline: fetch → analyze → format."""

    async def on_start(self) -> None:
        self.state["requests"] = 0

    async def handle(self, message: Message) -> Message | None:
        topic = message.payload.get("topic", "AI")
        self.state["requests"] += 1

        fetched = await self.ask("fetcher", {"topic": topic})
        analyzed = await self.ask("analyzer", fetched.payload)
        formatted = await self.ask(
            "formatter",
            {**analyzed.payload, "topic": topic},
        )

        return self.reply({
            "report": formatted.payload["report"],
            "requests_handled": self.state["requests"],
        })


async def main() -> None:
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            children=[
                Fetcher("fetcher"),
                Analyzer("analyzer"),
                Formatter("formatter"),
                Coordinator("coordinator"),
            ],
        )
    )
    await runtime.start()

    for topic in ["asyncio", "supervision trees", "NATS"]:
        reply = await runtime.ask("coordinator", {"topic": topic})
        print(reply.payload["report"])
        print()

    print(f"Total requests handled: {runtime.get_agent('coordinator').state['requests']}")
    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
