"""Level 3 — Supervisor process (NATS).

Connects to NATS and runs the frontend agent.
Override NATS_URL via environment variable if NATS is not on localhost.

    NATS_URL=nats://nats-host:4222 \
    uv run python examples/deployment/level3_distributed/run_supervisor.py
"""

import asyncio
import os
from pathlib import Path

from civitas import Runtime

TOPOLOGY = Path(__file__).parent / "topology.yaml"


async def main() -> None:
    nats_url = os.environ.get("NATS_URL", "nats://localhost:4222")
    runtime = Runtime.from_config(TOPOLOGY)
    await runtime.start()
    print(f"Supervisor connected to NATS ({nats_url})")
    print("Start the worker process on any machine, then send requests.")
    print("Press Ctrl+C to stop.\n")

    try:
        await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
