"""Agent definitions shared by supervisor and worker processes (Level 2)."""

from civitas import AgentProcess
from civitas.messages import Message


class FrontendAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        job = message.payload.get("job", "")
        result_a = await self.ask("worker_a", {"job": job, "shard": "A"})
        result_b = await self.ask("worker_b", {"job": job, "shard": "B"})
        return self.reply({
            "job": job,
            "results": [result_a.payload["output"], result_b.payload["output"]],
            "transport": "ZMQTransport",
        })


class WorkerAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        shard = message.payload.get("shard", "?")
        job = message.payload.get("job", "")
        return self.reply({"output": f"[worker_{shard.lower()}] processed {job!r}"})
