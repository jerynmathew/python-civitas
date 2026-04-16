"""Pattern: Fan-Out / Fan-In.

An Aggregator sends the same query to N workers in parallel using
asyncio.gather(), then combines all results before replying.

Use this when:
  - Tasks are independent and can run concurrently
  - You need results from all workers before proceeding
  - Latency matters — parallel beats sequential for I/O-bound work

Run:
    uv run python examples/patterns/fan_out_fan_in.py
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message


class DataWorker(AgentProcess):
    """Processes a single chunk. Simulate variable latency."""

    async def handle(self, message: Message) -> Message | None:
        chunk = message.payload.get("chunk", "")
        shard = message.payload.get("shard", 0)
        await asyncio.sleep(0.05 * (shard + 1))  # staggered fake I/O
        return self.reply(
            {
                "shard": shard,
                "result": f"processed({chunk})",
                "word_count": len(chunk.split()),
            }
        )


class Aggregator(AgentProcess):
    """Fans out to all workers in parallel, collects results."""

    WORKERS = ["worker_0", "worker_1", "worker_2", "worker_3"]

    async def handle(self, message: Message) -> Message | None:
        query = message.payload.get("query", "")

        # Split work across workers
        chunks = query.split()
        shards = [" ".join(chunks[i :: len(self.WORKERS)]) for i in range(len(self.WORKERS))]

        # Fan out — all workers run concurrently
        tasks = [
            self.ask(worker, {"chunk": shard, "shard": i})
            for i, (worker, shard) in enumerate(zip(self.WORKERS, shards, strict=False))
        ]
        replies = await asyncio.gather(*tasks)

        # Fan in — aggregate results
        total_words = sum(r.payload["word_count"] for r in replies)
        combined = " | ".join(r.payload["result"] for r in replies)

        return self.reply(
            {
                "combined": combined,
                "total_words": total_words,
                "worker_count": len(self.WORKERS),
            }
        )


async def main() -> None:
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            children=[
                Aggregator("aggregator"),
                DataWorker("worker_0"),
                DataWorker("worker_1"),
                DataWorker("worker_2"),
                DataWorker("worker_3"),
            ],
        )
    )
    await runtime.start()

    query = "the quick brown fox jumps over the lazy dog near the river bank"
    print(f"Query: {query!r}\n")

    start = asyncio.get_event_loop().time()
    reply = await runtime.ask("aggregator", {"query": query})
    elapsed = asyncio.get_event_loop().time() - start

    print(f"Workers:     {reply.payload['worker_count']}")
    print(f"Total words: {reply.payload['total_words']}")
    print(f"Combined:    {reply.payload['combined']}")
    print(f"Elapsed:     {elapsed:.3f}s  (sequential would be ~{0.05 * 10:.2f}s)")

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
