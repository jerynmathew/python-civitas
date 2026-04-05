"""agency dashboard — live terminal dashboard for a running topology."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.live import Live

from agency import Runtime
from agency.cli.app import app, console, err_console, register_shutdown, success
from agency.dashboard.collector import MetricsCollector
from agency.dashboard.renderer import render_dashboard


async def _run_dashboard(
    topology_path: Path,
    refresh_rate: float,
) -> None:
    """Start the runtime with metrics collection and render a live dashboard."""
    collector = MetricsCollector()
    runtime = Runtime.from_config(str(topology_path))

    # FD-01: wire restart events into MetricsCollector via lightweight hook
    if runtime._root_supervisor is not None:
        original_handle_crash = runtime._root_supervisor._handle_crash

        async def _instrumented_crash(name: str, exc: Exception) -> None:
            collector.agent_restarted(name, type(exc).__name__)
            await original_handle_crash(name, exc)

        runtime._root_supervisor._handle_crash = _instrumented_crash  # type: ignore[method-assign]

    await runtime.start()
    collector.runtime_started()

    # Register all agents and set initial status
    for agent in runtime.all_agents():
        collector.register_agent(agent.name)
        collector.agent_status_changed(agent.name, agent.status.value)

    stop_event = asyncio.Event()
    register_shutdown(stop_event)

    with Live(render_dashboard(collector), refresh_per_second=1 / refresh_rate, console=console):
        while not stop_event.is_set():
            # Update agent statuses
            for agent in runtime.all_agents():
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

    asyncio.run(_run_dashboard(topology_path, refresh))
