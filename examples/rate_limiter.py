"""Rate limiter example — GenServer with a token-bucket and recurring timer.

Demonstrates:
- GenServer with init(), handle_call, handle_cast, handle_info
- send_after() for recurring self-messages (token refill tick)
- AgentProcess calling a sibling GenServer via self.call() / self.cast()

Run:
    uv run python examples/rate_limiter.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from civitas import AgentProcess, GenServer, Runtime, Supervisor
from civitas.messages import Message


class RateLimiter(GenServer):
    """Token-bucket rate limiter.

    Configuration (via init_config passed as constructor kwargs):
    - capacity: maximum tokens in the bucket (default 10)
    - refill_amount: tokens added per tick (default 2)
    - refill_interval_ms: tick interval in milliseconds (default 1000)

    Supports:
    - call {"op": "acquire"} → {"ok": True/False, "remaining": N}
    - cast {"op": "reset"}   → reset bucket to capacity
    """

    def __init__(
        self,
        name: str,
        capacity: int = 10,
        refill_amount: int = 2,
        refill_interval_ms: int = 1000,
    ) -> None:
        super().__init__(name)
        self._capacity = capacity
        self._refill_amount = refill_amount
        self._refill_interval_ms = refill_interval_ms

    async def init(self) -> None:
        self.state["tokens"] = self._capacity
        self.state["total_acquired"] = 0
        self.state["total_rejected"] = 0
        # Schedule the first refill tick
        self.send_after(self._refill_interval_ms, {"type": "refill"})

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        op = payload.get("op")
        if op == "acquire":
            if self.state["tokens"] > 0:
                self.state["tokens"] -= 1
                self.state["total_acquired"] += 1
                return {"ok": True, "remaining": self.state["tokens"]}
            self.state["total_rejected"] += 1
            return {"ok": False, "remaining": 0}
        if op == "stats":
            return {
                "tokens": self.state["tokens"],
                "capacity": self._capacity,
                "total_acquired": self.state["total_acquired"],
                "total_rejected": self.state["total_rejected"],
            }
        return {"error": f"unknown op: {op}"}

    async def handle_cast(self, payload: dict[str, Any]) -> None:
        if payload.get("op") == "reset":
            self.state["tokens"] = self._capacity

    async def handle_info(self, payload: dict[str, Any]) -> None:
        if payload.get("type") == "refill":
            self.state["tokens"] = min(self._capacity, self.state["tokens"] + self._refill_amount)
            # Reschedule next tick
            self.send_after(self._refill_interval_ms, {"type": "refill"})


class WorkerAgent(AgentProcess):
    """Simulates request bursts through the rate limiter."""

    async def on_start(self) -> None:
        # Trigger our demo sequence after a short settle
        self.send_after_demo()

    def send_after_demo(self) -> None:
        asyncio.get_event_loop().call_soon(lambda: asyncio.ensure_future(self._run_demo()))

    async def _run_demo(self) -> None:
        await asyncio.sleep(0.1)  # let the runtime settle

        print("\n=== Token-bucket rate limiter demo ===\n")

        # Drain the bucket
        print("Sending 12 rapid requests (bucket capacity = 10):")
        for i in range(12):
            result = await self.call("limiter", {"op": "acquire"})
            status = "✓" if result["ok"] else "✗ REJECTED"
            print(f"  Request {i + 1:2d}: {status}  (remaining: {result['remaining']})")

        stats = await self.call("limiter", {"op": "stats"})
        print(f"\nStats: {stats}")

        # Reset via cast
        print("\nResetting bucket via cast...")
        await self.cast("limiter", {"op": "reset"})
        await asyncio.sleep(0.05)

        stats = await self.call("limiter", {"op": "stats"})
        print(f"Stats after reset: {stats}")
        print("\nDone.")

    async def handle(self, message: Message) -> Message | None:
        return None


async def main() -> None:
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            children=[
                RateLimiter("limiter", capacity=10, refill_amount=2, refill_interval_ms=500),
                WorkerAgent("worker"),
            ],
        )
    )
    await runtime.start()
    await asyncio.sleep(1.0)
    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
