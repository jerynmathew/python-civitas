"""Quickstart 1: Hello Agent.

The simplest Agency program. One agent, one message, one reply.
No LLM, no tools — pure runtime mechanics.

Run:
    uv run python examples/quickstart/01_hello_agent.py
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message


class Greeter(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        name = message.payload.get("name", "world")
        print(f"  [greeter] Hello, {name}!")
        return self.reply({"greeting": f"Hello, {name}!"})


async def main() -> None:
    runtime = Runtime(
        supervisor=Supervisor("root", children=[Greeter("greeter")])
    )
    await runtime.start()

    reply = await runtime.ask("greeter", {"name": "Agency"})
    print(f"  [runtime] Got reply: {reply.payload}")

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
