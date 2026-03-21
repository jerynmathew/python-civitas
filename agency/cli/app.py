"""Shared CLI application instance, consoles, and output helpers.

Every CLI module imports from here — this is the single source for the
root Typer app, Rich consoles, and consistent output formatting.
"""

from __future__ import annotations

import asyncio
import signal
import sys

import typer
from rich.console import Console

app = typer.Typer(
    name="agency",
    help="The production runtime for Python agents.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Output helpers — ensure visual consistency across all commands
# ---------------------------------------------------------------------------


def success(msg: str) -> None:
    """Print a success message with green checkmark."""
    console.print(f"  [green]✔[/green] {msg}")


def error(msg: str) -> None:
    """Print an error message with red X to stderr."""
    err_console.print(f"  [red]✗[/red] {msg}")


def info(msg: str) -> None:
    """Print an info message in blue."""
    console.print(f"  [blue]{msg}[/blue]")


def warn(msg: str) -> None:
    """Print a warning message in yellow."""
    console.print(f"  [yellow]{msg}[/yellow]")


def section(title: str) -> None:
    """Print a section header (dim, indented)."""
    console.print(f"\n  [bold]{title}[/bold]")


def register_shutdown(stop_event: asyncio.Event) -> None:
    """Wire SIGINT/SIGTERM to set *stop_event*, cross-platform.

    On Unix, ``loop.add_signal_handler`` is used for clean async shutdown.
    On Windows, ``add_signal_handler`` is not supported, so we fall back to
    ``signal.signal`` which raises ``KeyboardInterrupt`` on Ctrl+C — the
    caller should catch it and shut down gracefully.
    """
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
    else:
        # Windows: SIGTERM doesn't exist; SIGINT is delivered as
        # KeyboardInterrupt. We install a signal handler that sets the
        # event so the await-based shutdown path still works.
        def _handler(signum: int, frame: object) -> None:
            stop_event.set()

        signal.signal(signal.SIGINT, _handler)
