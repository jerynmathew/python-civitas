"""Level 2 — Supervisor process.

Starts the ZMQ proxy and runs the frontend agent.
Run this before run_worker.py.

    uv run python examples/deployment/level2_multi_process/run_supervisor.py
"""

import asyncio
from pathlib import Path

from civitas import Runtime

TOPOLOGY = Path(__file__).parent / "topology.yaml"


async def main() -> None:
    runtime = Runtime.from_config(TOPOLOGY)
    await runtime.start()
    print("Supervisor running. Start the worker process, then send a request.")
    print("Press Ctrl+C to stop.\n")

    # In a real app, a web server or queue consumer would drive this.
    # Here we just wait for keyboard interrupt.
    try:
        await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
