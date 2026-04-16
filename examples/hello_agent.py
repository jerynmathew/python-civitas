"""Hello Agent: The simplest Agency program.

A single agent receives a message and responds. Under 15 lines of user code.
No LLM, no tools — pure runtime mechanics.
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor


class Greeter(AgentProcess):
    async def handle(self, message):
        print(f"Hello, {message.payload['name']}!")
        return self.reply({"status": "ok"})


async def main():
    runtime = Runtime(supervisor=Supervisor("root", children=[Greeter("greeter")]))
    await runtime.start()
    result = await runtime.ask("greeter", {"name": "world"})
    print(f"Reply: {result.payload}")
    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
