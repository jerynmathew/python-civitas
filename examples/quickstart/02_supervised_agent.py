"""Quickstart 2: Supervised Agent.

A deliberately flaky agent crashes on every third message. The supervisor
detects the crash, waits briefly, and restarts it — automatically.
Your code never sees the failure.

Run:
    uv run python examples/quickstart/02_supervised_agent.py
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message


class FlakyCounter(AgentProcess):
    """Counts messages. Crashes on every third one."""

    async def on_start(self) -> None:
        self.state["count"] = self.state.get("count", 0)

    async def handle(self, message: Message) -> Message | None:
        self.state["count"] += 1
        n = self.state["count"]

        if n % 3 == 0:
            raise RuntimeError(f"Deliberate crash on message {n}")

        return self.reply({"count": n})


async def main() -> None:
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            strategy="ONE_FOR_ONE",
            max_restarts=10,
            backoff="CONSTANT",
            backoff_base=0.05,      # 50 ms — fast for the demo
            children=[FlakyCounter("counter")],
        )
    )
    await runtime.start()

    for i in range(1, 9):
        try:
            reply = await runtime.ask("counter", {}, timeout=2.0)
            print(f"  message {i} → count={reply.payload['count']}")
        except TimeoutError:
            print(f"  message {i} → timed out (agent restarting)")

    await runtime.stop()
    print("\nDone. The supervisor handled all crashes transparently.")


if __name__ == "__main__":
    asyncio.run(main())
