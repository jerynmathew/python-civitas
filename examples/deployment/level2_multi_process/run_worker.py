"""Level 2 — Worker process.

Connects to the ZMQ proxy started by run_supervisor.py and hosts
worker_a and worker_b.

    uv run python examples/deployment/level2_multi_process/run_worker.py
"""

import asyncio
from pathlib import Path

from agency.worker import Worker

TOPOLOGY = Path(__file__).parent / "topology.yaml"


async def main() -> None:
    worker = Worker.from_config(TOPOLOGY, process_name="worker")
    await worker.start()
    print("Worker process running (worker_a, worker_b). Press Ctrl+C to stop.")

    try:
        await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
