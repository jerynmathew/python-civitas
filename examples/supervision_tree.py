"""M1.6 — Supervision Tree: YAML config and ASCII tree visualization.

Loads a topology from YAML and prints the tree structure.
"""

import asyncio
from pathlib import Path

from agency import AgentProcess, Runtime
from agency.messages import Message


class Researcher(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        return self.reply({"findings": f"Research from {self.name}"})


class Summarizer(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        return self.reply({"summary": f"Summarized by {self.name}"})


async def main():
    # Load from YAML
    config_path = Path(__file__).parent / "topology.yaml"
    runtime = Runtime.from_config(
        config_path,
        agent_classes={"Researcher": Researcher, "Summarizer": Summarizer},
    )

    print("=== Supervision Tree ===")
    print(runtime.print_tree())
    print()

    await runtime.start()

    # Send messages to verify agents work
    r1 = await runtime.ask("researcher_1", {"topic": "AI"})
    r2 = await runtime.ask("summarizer", {"text": "some text"})
    print(f"Researcher: {r1.payload}")
    print(f"Summarizer: {r2.payload}")

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
