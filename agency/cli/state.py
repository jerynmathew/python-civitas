"""agency state — manage persisted agent state."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.table import Table

from agency.cli.app import console, success, warn
from agency.plugins.sqlite_store import SQLiteStateStore

state_app = typer.Typer(
    name="state",
    help="Manage persisted agent state.",
    no_args_is_help=True,
)


@state_app.command("list")
def state_list(
    db: str = typer.Option("agency_state.db", "--db", help="SQLite database path"),
) -> None:
    """Show all persisted agent states."""
    db_path = Path(db)
    if not db_path.exists():
        warn(f"No state database found at '{db}'.")
        raise typer.Exit(0)

    store = SQLiteStateStore(str(db_path))
    agents = asyncio.run(store.list_agents())

    if not agents:
        warn("No persisted agent states found.")
        store.close()
        return

    table = Table(title="Persisted Agent States", show_lines=True)
    table.add_column("Agent", style="cyan")
    table.add_column("State", style="white", overflow="fold")

    for agent_name in agents:
        state = asyncio.run(store.get(agent_name))
        state_str = json.dumps(state, indent=2) if state else "{}"
        table.add_row(agent_name, state_str)

    console.print(table)
    store.close()


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

    store = SQLiteStateStore(str(db_path))

    if agent_name:
        state = asyncio.run(store.get(agent_name))
        if state is None:
            warn(f"No state found for agent '{agent_name}'.")
            store.close()
            return
        if not force:
            confirm = typer.confirm(f"Clear state for agent '{agent_name}'?")
            if not confirm:
                raise typer.Abort()
        asyncio.run(store.delete(agent_name))
        success(f"Cleared state for agent '{agent_name}'.")
    else:
        agents = asyncio.run(store.list_agents())
        if not agents:
            warn("No persisted agent states found.")
            store.close()
            return
        if not force:
            confirm = typer.confirm(f"Clear state for ALL {len(agents)} agents?")
            if not confirm:
                raise typer.Abort()
        for name in agents:
            asyncio.run(store.delete(name))
        success(f"Cleared state for {len(agents)} agents.")

    store.close()
