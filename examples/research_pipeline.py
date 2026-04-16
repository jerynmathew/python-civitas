"""Multi-Agent Communication: A three-agent research pipeline.

Coordinator sends tasks to Researcher, who sends results to Summarizer.
Demonstrates send, ask, broadcast, and pattern-based routing.
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message


class Researcher(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        topic = message.payload.get("topic", "unknown")
        return self.reply({"findings": f"Research results for: {topic}"})


class Summarizer(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        findings = message.payload.get("findings", "")
        return self.reply({"summary": f"Summary of [{findings}]"})


class Coordinator(AgentProcess):
    async def on_start(self) -> None:
        self.state["tasks_completed"] = 0

    async def handle(self, message: Message) -> Message | None:
        topic = message.payload.get("topic", "general")

        # Ask researcher for findings
        research = await self.ask("researcher", {"topic": topic})

        # Ask summarizer to condense
        summary = await self.ask("summarizer", {"findings": research.payload["findings"]})

        self.state["tasks_completed"] += 1
        return self.reply(
            {
                "topic": topic,
                "summary": summary.payload["summary"],
                "tasks_completed": self.state["tasks_completed"],
            }
        )


async def main():
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            children=[
                Researcher("researcher"),
                Summarizer("summarizer"),
                Coordinator("coordinator"),
            ],
        )
    )
    await runtime.start()

    result = await runtime.ask("coordinator", {"topic": "Python asyncio"})
    print(f"Result: {result.payload}")

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
