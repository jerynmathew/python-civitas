"""civitas version — show the Civitas version."""

from __future__ import annotations

from civitas.cli.app import app, console


@app.command()
def version() -> None:
    """Show the Civitas version."""
    console.print("[cyan]civitas[/cyan] version [green]0.1.0[/green]")
