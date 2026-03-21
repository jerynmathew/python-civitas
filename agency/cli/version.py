"""agency version — show the Agency version."""

from __future__ import annotations

from agency.cli.app import app, console


@app.command()
def version() -> None:
    """Show the Agency version."""
    console.print("[cyan]python-agency[/cyan] version [green]0.1.0[/green]")
