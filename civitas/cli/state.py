"""civitas state — manage persisted agent state."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer
from rich.table import Table

from civitas.cli.app import console, success, warn
from civitas.plugins.sqlite_store import SQLiteStateStore

state_app = typer.Typer(
    name="state",
    help="Manage persisted agent state.",
    no_args_is_help=True,
)


async def _load_all_states(
    db_path: str,
) -> tuple[list[str], dict[str, dict[str, Any] | None]]:
    """Fetch all agent names and their states in a single event loop."""
    store = SQLiteStateStore(db_path)
    try:
        agents = await store.list_agents()
        states = {name: await store.get(name) for name in agents}
        return agents, states
    finally:
        await store.close()


async def _delete_agents(db_path: str, names: list[str]) -> None:
    """Delete state for each name in a single event loop."""
    store = SQLiteStateStore(db_path)
    try:
        for name in names:
            await store.delete(name)
    finally:
        await store.close()


@state_app.command("list")
def state_list(
    db: str = typer.Option("agency_state.db", "--db", help="SQLite database path"),
) -> None:
    """Show all persisted agent states."""
    db_path = Path(db)
    if not db_path.exists():
        warn(f"No state database found at '{db}'.")
        raise typer.Exit(0)

    agents, states = asyncio.run(_load_all_states(str(db_path)))

    if not agents:
        warn("No persisted agent states found.")
        return

    table = Table(title="Persisted Agent States", show_lines=True)
    table.add_column("Agent", style="cyan")
    table.add_column("State", style="white", overflow="fold")

    for agent_name in agents:
        state_str = json.dumps(states.get(agent_name), indent=2) if states.get(agent_name) else "{}"
        table.add_row(agent_name, state_str)

    console.print(table)


@state_app.command("clear")
def state_clear(
    agent_name: str | None = typer.Argument(None, help="Agent name to clear (omit for all)"),
    db: str = typer.Option("agency_state.db", "--db", help="SQLite database path"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Clear persisted agent state."""
    db_path = Path(db)
    if not db_path.exists():
        warn(f"No state database found at '{db}'.")
        raise typer.Exit(0)

    agents, states = asyncio.run(_load_all_states(str(db_path)))

    if agent_name:
        if agent_name not in states or states[agent_name] is None:
            warn(f"No state found for agent '{agent_name}'.")
            return
        if not force:
            confirm = typer.confirm(f"Clear state for agent '{agent_name}'?")
            if not confirm:
                raise typer.Abort()
        asyncio.run(_delete_agents(str(db_path), [agent_name]))
        success(f"Cleared state for agent '{agent_name}'.")
    else:
        if not agents:
            warn("No persisted agent states found.")
            return
        if not force:
            confirm = typer.confirm(f"Clear state for ALL {len(agents)} agents?")
            if not confirm:
                raise typer.Abort()
        asyncio.run(_delete_agents(str(db_path), agents))
        success(f"Cleared state for {len(agents)} agents.")
