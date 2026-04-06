"""Level 3 — Worker process (NATS).

Connects to the same NATS server as the supervisor and hosts worker_a/worker_b.
Can run on a completely different machine — only needs NATS connectivity.

    NATS_URL=nats://supervisor-host:4222 \
    uv run python examples/deployment/level3_distributed/run_worker.py
"""

import asyncio
import os
from pathlib import Path

from agency.worker import Worker

TOPOLOGY = Path(__file__).parent / "topology.yaml"


async def main() -> None:
    nats_url = os.environ.get("NATS_URL", "nats://localhost:4222")
    worker = Worker.from_config(TOPOLOGY, process_name="worker")
    await worker.start()
    print(f"Worker connected to NATS ({nats_url}) — hosting worker_a, worker_b")
    print("Press Ctrl+C to stop.")

    try:
        await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
