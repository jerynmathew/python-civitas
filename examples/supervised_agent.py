"""Supervised Agent: Crash recovery with restart strategies.

A flaky agent that crashes occasionally. The supervisor detects the crash,
applies backoff, and restarts the agent — all automatically.
"""

import asyncio
import random

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message


class FlakyWorker(AgentProcess):
    """Agent that randomly crashes ~30% of the time."""

    async def handle(self, message: Message) -> Message | None:
        if random.random() < 0.3:
            raise RuntimeError("Temporary failure!")
        return self.reply({"result": f"processed: {message.payload.get('task')}"})


async def main():
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            strategy="ONE_FOR_ONE",
            max_restarts=5,
            restart_window=60.0,
            backoff="EXPONENTIAL",
            backoff_base=0.1,
            children=[FlakyWorker("worker")],
        )
    )
    await runtime.start()

    for i in range(5):
        try:
            result = await runtime.ask("worker", {"task": f"job-{i}"}, timeout=5.0)
            print(f"Task {i}: {result.payload}")
        except Exception as e:
            print(f"Task {i}: failed ({e})")

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
