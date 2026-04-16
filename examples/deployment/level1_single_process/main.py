"""Deployment Level 1: Single Process (InProcessTransport).

All agents run as asyncio tasks in one Python process. No extra dependencies.
This is the development default and works fine for I/O-bound workloads.

Run:
    uv run python examples/deployment/level1_single_process/main.py

Upgrade to Level 2: change transport.type to zmq in topology.yaml
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message


class FrontendAgent(AgentProcess):
    """Receives requests and delegates to backend agents."""

    async def handle(self, message: Message) -> Message | None:
        job = message.payload.get("job", "")
        result_a = await self.ask("worker_a", {"job": job, "shard": "A"})
        result_b = await self.ask("worker_b", {"job": job, "shard": "B"})
        return self.reply(
            {
                "job": job,
                "results": [result_a.payload["output"], result_b.payload["output"]],
                "transport": "InProcessTransport",
            }
        )


class WorkerAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        shard = message.payload.get("shard", "?")
        job = message.payload.get("job", "")
        return self.reply({"output": f"[worker_{shard.lower()}] processed {job!r}"})


async def main() -> None:
    # Level 1: InProcessTransport (default — no transport= arg needed)
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            strategy="ONE_FOR_ONE",
            max_restarts=5,
            children=[
                FrontendAgent("frontend"),
                WorkerAgent("worker_a"),
                WorkerAgent("worker_b"),
            ],
        )
    )

    await runtime.start()
    print("Transport: InProcessTransport\n")

    for job in ["render-report", "export-csv", "send-digest"]:
        reply = await runtime.ask("frontend", {"job": job})
        print(f"Job: {reply.payload['job']}")
        for r in reply.payload["results"]:
            print(f"  {r}")

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
