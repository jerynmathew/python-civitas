"""Pattern: Sequential Pipeline.

A fixed chain of agents where each stage transforms the message and passes
the result to the next stage. The final stage replies to the original caller.

Use this when:
  - Each step depends on the previous step's output
  - You want each stage independently supervised and restartable
  - The pipeline has a defined start and end

Stages: Ingest → Validate → Enrich → Store → Reply

Run:
    uv run python examples/patterns/pipeline.py
"""

import asyncio

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message


class IngestStage(AgentProcess):
    """Normalises incoming raw data."""

    async def handle(self, message: Message) -> Message | None:
        raw = message.payload.get("raw", "")
        normalised = raw.strip().lower()
        print(f"  [ingest]   {raw!r} → {normalised!r}")
        return self.reply({"data": normalised, "source": message.payload.get("source", "unknown")})


class ValidateStage(AgentProcess):
    """Rejects empty or too-short data."""

    async def handle(self, message: Message) -> Message | None:
        data = message.payload.get("data", "")
        if len(data) < 3:
            return self.reply({"error": f"too short: {data!r}", "valid": False})
        print(f"  [validate] ok ({len(data)} chars)")
        return self.reply({**message.payload, "valid": True, "length": len(data)})


class EnrichStage(AgentProcess):
    """Adds metadata to valid records."""

    async def handle(self, message: Message) -> Message | None:
        if not message.payload.get("valid"):
            return self.reply(message.payload)  # pass errors through
        data = message.payload.get("data", "")
        enriched = {
            **message.payload,
            "word_count": len(data.split()),
            "tags": [w for w in data.split() if len(w) > 4],
        }
        print(f"  [enrich]   words={enriched['word_count']} tags={enriched['tags']}")
        return self.reply(enriched)


class StoreStage(AgentProcess):
    """Persists the record (simulated) and returns a record ID."""

    async def on_start(self) -> None:
        self.state["next_id"] = self.state.get("next_id", 1)

    async def handle(self, message: Message) -> Message | None:
        if not message.payload.get("valid"):
            return self.reply(message.payload)
        record_id = f"rec_{self.state['next_id']:04d}"
        self.state["next_id"] += 1
        print(f"  [store]    saved as {record_id}")
        return self.reply({**message.payload, "record_id": record_id})


class PipelineEntry(AgentProcess):
    """Entry point — drives all stages in order and returns the final result."""

    STAGES = ["ingest", "validate", "enrich", "store"]

    async def handle(self, message: Message) -> Message | None:
        payload = message.payload
        for stage in self.STAGES:
            reply = await self.ask(stage, payload)
            payload = reply.payload
            if payload.get("error"):
                break  # short-circuit on validation failure
        return self.reply(payload)


async def main() -> None:
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            children=[
                PipelineEntry("pipeline"),
                IngestStage("ingest"),
                ValidateStage("validate"),
                EnrichStage("enrich"),
                StoreStage("store"),
            ],
        )
    )
    await runtime.start()

    records = [
        {"raw": "  Hello Agency World  ", "source": "api"},
        {"raw": "ok", "source": "api"},           # too short — validation fails
        {"raw": "Supervision trees are great", "source": "web"},
    ]

    for record in records:
        print(f"\nInput: {record}")
        reply = await runtime.ask("pipeline", record)
        result = reply.payload
        if result.get("error"):
            print(f"  Result: REJECTED — {result['error']}")
        else:
            print(f"  Result: {result['record_id']} (words={result['word_count']})")

    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
