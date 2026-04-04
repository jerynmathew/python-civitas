"""agency dashboard — live terminal dashboard for a running topology."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.live import Live

from agency import Runtime
from agency.cli.app import app, console, err_console, register_shutdown, success
from agency.dashboard.collector import MetricsCollector
from agency.dashboard.renderer import render_dashboard


async def _run_dashboard(
    topology_path: Path,
    config: dict[str, Any],
    refresh_rate: float,
) -> None:
    """Start the runtime with metrics collection and render a live dashboard."""
    collector = MetricsCollector()
    runtime = Runtime.from_config(str(topology_path))

    await runtime.start()
    collector.runtime_started()

    # Register all agents and set initial status
    if runtime._root_supervisor is not None:
        for agent in runtime._root_supervisor.all_agents():
            collector.register_agent(agent.name)
            collector.agent_status_changed(agent.name, agent.status.value)

    stop_event = asyncio.Event()
    register_shutdown(stop_event)

    with Live(render_dashboard(collector), refresh_per_second=1 / refresh_rate, console=console):
        while not stop_event.is_set():
            # Update agent statuses
            if runtime._root_supervisor is not None:
                for agent in runtime._root_supervisor.all_agents():
                    collector.agent_status_changed(agent.name, agent.status.value)

            await asyncio.sleep(refresh_rate)

    console.print("\n  [yellow]Shutting down...[/yellow]")
    await runtime.stop()
    success("Stopped")


@app.command()
def dashboard(
    topology: str = typer.Option("topology.yaml", "--topology", "-t", help="Topology YAML file"),
    refresh: float = typer.Option(1.0, "--refresh", "-r", help="Refresh rate in seconds"),
) -> None:
    """Launch a live terminal dashboard for a running topology."""
    topology_path = Path(topology)
    if not topology_path.exists():
        err_console.print(f"[red]Error:[/red] Topology file '{topology}' not found.")
        raise typer.Exit(1)

    config = yaml.safe_load(topology_path.read_text())
    asyncio.run(_run_dashboard(topology_path, config, refresh))
