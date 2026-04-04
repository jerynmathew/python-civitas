"""Terminal dashboard renderer — Rich-based live display.

Renders a MetricsCollector snapshot as a Rich Layout with:
- Supervision tree with live agent status
- Message flow statistics
- Cost attribution per agent
- Restart history
"""

from __future__ import annotations

import time
from typing import Any

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from agency.dashboard.collector import MetricsCollector, RuntimeSnapshot

_STATUS_COLORS = {
    "running": "green",
    "initializing": "yellow",
    "restarting": "yellow",
    "stopped": "dim",
    "crashed": "red",
    "unknown": "dim",
}

_STATUS_DOTS = {
    "running": "●",
    "initializing": "◐",
    "restarting": "○",
    "stopped": "○",
    "crashed": "✗",
    "unknown": "?",
}


def _format_uptime(seconds: float) -> str:
    """Format seconds into a human-readable uptime string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins}m"


def _format_cost(cost: float) -> str:
    """Format cost as a dollar amount."""
    if cost == 0:
        return "-"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _format_timestamp(ts: float | None) -> str:
    """Format a timestamp as relative time ago."""
    if ts is None:
        return "-"
    ago = time.time() - ts
    if ago < 60:
        return f"{ago:.0f}s ago"
    if ago < 3600:
        return f"{ago / 60:.0f}m ago"
    return f"{ago / 3600:.1f}h ago"


def render_supervision_tree(
    snapshot: RuntimeSnapshot,
    tree_config: dict[str, Any] | None = None,
) -> Tree:
    """Render the supervision tree with live agent status indicators.

    Args:
        snapshot: Current runtime metrics snapshot.
        tree_config: Optional topology config for tree structure.
                     If None, renders a flat agent list.
    """
    tree = Tree("[bold cyan]Agency Runtime[/bold cyan]")

    if not snapshot.agents:
        tree.add("[dim]No agents registered[/dim]")
        return tree

    for name, metrics in sorted(snapshot.agents.items()):
        color = _STATUS_COLORS.get(metrics.status, "dim")
        dot = _STATUS_DOTS.get(metrics.status, "?")

        label = Text()
        label.append(f"{dot} ", style=color)
        label.append(f"{name}", style=f"bold {color}")
        label.append(f"  msgs: {metrics.messages_handled}", style="dim")
        if metrics.restarts > 0:
            label.append(f"  restarts: {metrics.restarts}", style="yellow")

        tree.add(label)

    return tree


def render_message_stats(snapshot: RuntimeSnapshot) -> Table:
    """Render per-agent message statistics table."""
    table = Table(title="Message Flow", show_lines=False, expand=True)
    table.add_column("Agent", style="cyan")
    table.add_column("Handled", justify="right")
    table.add_column("Sent", justify="right")
    table.add_column("Avg Latency", justify="right")
    table.add_column("Errors", justify="right")
    table.add_column("Last Active", justify="right")

    for name, m in sorted(snapshot.agents.items()):
        latency_str = f"{m.avg_latency_ms:.1f}ms" if m.messages_handled > 0 else "-"
        error_style = "red" if m.errors > 0 else "dim"
        table.add_row(
            name,
            str(m.messages_handled),
            str(m.messages_sent),
            latency_str,
            Text(str(m.errors), style=error_style),
            _format_timestamp(m.last_active),
        )

    return table


def render_cost_attribution(snapshot: RuntimeSnapshot) -> Table:
    """Render per-agent cost and token usage table."""
    table = Table(title="Cost Attribution", show_lines=False, expand=True)
    table.add_column("Agent", style="cyan")
    table.add_column("Tokens In", justify="right")
    table.add_column("Tokens Out", justify="right")
    table.add_column("Cost", justify="right", style="green")

    has_cost_data = False
    for name, m in sorted(snapshot.agents.items()):
        if m.tokens_in > 0 or m.tokens_out > 0 or m.cost_usd > 0:
            has_cost_data = True
            table.add_row(
                name,
                f"{m.tokens_in:,}",
                f"{m.tokens_out:,}",
                _format_cost(m.cost_usd),
            )

    if not has_cost_data:
        table.add_row("[dim]No LLM calls recorded[/dim]", "", "", "")

    if snapshot.total_cost_usd > 0:
        table.add_row(
            "[bold]Total[/bold]",
            "",
            "",
            f"[bold green]{_format_cost(snapshot.total_cost_usd)}[/bold green]",
        )

    return table


def render_restart_history(snapshot: RuntimeSnapshot, limit: int = 10) -> Table:
    """Render recent restart events."""
    table = Table(title="Restart History", show_lines=False, expand=True)
    table.add_column("Agent", style="cyan")
    table.add_column("When", justify="right")
    table.add_column("Reason", style="dim")

    events = snapshot.restart_history[-limit:]
    if not events:
        table.add_row("[dim]No restarts[/dim]", "", "")
    else:
        for event in reversed(events):
            table.add_row(
                event.agent_name,
                _format_timestamp(event.timestamp),
                event.reason or "-",
            )

    return table


def render_dashboard(collector: MetricsCollector) -> Layout:
    """Render the full dashboard layout.

    Returns a Rich Layout suitable for use with ``rich.live.Live``.
    """
    snapshot = collector.snapshot

    # Header
    uptime = _format_uptime(snapshot.uptime_seconds)
    total_msgs = snapshot.total_messages
    agent_count = len(snapshot.agents)
    header_text = (
        f"[bold cyan]Agency Dashboard[/bold cyan]  "
        f"[dim]Uptime: {uptime}  "
        f"Agents: {agent_count}  "
        f"Messages: {total_msgs}  "
        f"Cost: {_format_cost(snapshot.total_cost_usd)}[/dim]"
    )

    layout = Layout()
    layout.split_column(
        Layout(Panel(header_text, style="cyan"), size=3, name="header"),
        Layout(name="body"),
        Layout(name="footer"),
    )

    layout["body"].split_row(
        Layout(Panel(render_supervision_tree(snapshot), title="Supervision Tree"), name="tree"),
        Layout(Panel(render_message_stats(snapshot), title="Messages"), name="messages"),
    )

    layout["footer"].split_row(
        Layout(Panel(render_cost_attribution(snapshot), title="Costs"), name="costs"),
        Layout(Panel(render_restart_history(snapshot), title="Restarts"), name="restarts"),
    )

    return layout
