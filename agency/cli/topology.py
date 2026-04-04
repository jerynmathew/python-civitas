"""agency topology — validate, visualize, and diff topology files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml
from rich.rule import Rule
from rich.tree import Tree

from agency.cli.app import console, err_console, error, section, success

topology_app = typer.Typer(
    name="topology",
    help="Validate, visualize, and diff topology files.",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_STRATEGIES = {"ONE_FOR_ONE", "ONE_FOR_ALL", "REST_FOR_ONE"}
_VALID_BACKOFF = {"CONSTANT", "LINEAR", "EXPONENTIAL"}
_VALID_TRANSPORTS = {"in_process", "zmq", "nats"}


# ---------------------------------------------------------------------------
# Validation engine
# ---------------------------------------------------------------------------


class _ValidationResult:
    """Collects categorized validation results."""

    def __init__(self) -> None:
        self.checks: list[tuple[str, str, bool]] = []  # (category, message, passed)

    def ok(self, category: str, msg: str) -> None:
        self.checks.append((category, msg, True))

    def fail(self, category: str, msg: str) -> None:
        self.checks.append((category, msg, False))

    @property
    def passed(self) -> bool:
        return all(c[2] for c in self.checks)

    @property
    def error_count(self) -> int:
        return sum(1 for c in self.checks if not c[2])

    def print(self) -> None:
        """Print grouped validation results."""
        current_category = ""
        for category, msg, ok in self.checks:
            if category != current_category:
                section(category)
                current_category = category
            if ok:
                success(msg)
            else:
                error(msg)


def _validate_topology(config: dict[str, Any]) -> _ValidationResult:
    """Run all validation checks on a topology config."""
    result = _ValidationResult()

    # --- Structure ---
    try:
        yaml.safe_dump(config)
        result.ok("Structure", "YAML syntax")
    except yaml.YAMLError:
        result.fail("Structure", "YAML syntax invalid")
        return result

    sup = config.get("supervision", config.get("supervisor"))
    if sup is None:
        result.fail("Structure", "Missing 'supervision' section")
        return result
    result.ok("Structure", "Supervision section present")

    agent_names: list[str] = []
    supervisor_names: list[str] = []
    has_empty_sup = False

    def _validate_node(node: dict[str, Any], path: str) -> None:
        nonlocal has_empty_sup

        if "supervisor" in node:
            s = node["supervisor"]
            name = s.get("name", "<unnamed>")
            supervisor_names.append(name)

            strategy = s.get("strategy", "one_for_one").upper()
            if strategy not in _VALID_STRATEGIES:
                result.fail("Configuration", f"{path}.{name}: invalid strategy '{strategy}'")

            backoff = s.get("backoff", "constant").upper()
            if backoff not in _VALID_BACKOFF:
                result.fail("Configuration", f"{path}.{name}: invalid backoff '{backoff}'")

            max_restarts = s.get("max_restarts", 3)
            if not isinstance(max_restarts, int) or max_restarts < 0:
                result.fail(
                    "Configuration", f"{path}.{name}: max_restarts must be non-negative int"
                )

            children = s.get("children", [])
            if not children:
                has_empty_sup = True

            for child in children:
                _validate_node(child, f"{path}.{name}")

        elif "agent" in node:
            a = node["agent"]
            name = a.get("name")
            agent_type = a.get("type")
            if not name:
                result.fail("Naming", f"{path}: agent missing 'name'")
            if not agent_type:
                result.fail("Naming", f"{path}: agent missing 'type'")
            if name:
                agent_names.append(name)
        else:
            result.fail("Structure", f"{path}: node is neither 'supervisor' nor 'agent'")

    root_name = sup.get("name", "root")
    supervisor_names.append(root_name)

    # Validate root supervisor config
    root_strategy = sup.get("strategy", "one_for_one").upper()
    if root_strategy not in _VALID_STRATEGIES:
        result.fail("Configuration", f"root: invalid strategy '{root_strategy}'")

    root_backoff = sup.get("backoff", "constant").upper()
    if root_backoff not in _VALID_BACKOFF:
        result.fail("Configuration", f"root: invalid backoff '{root_backoff}'")

    children = sup.get("children", [])
    if not children:
        has_empty_sup = True

    for child in children:
        _validate_node(child, "root")

    if has_empty_sup:
        result.fail("Structure", "Supervisor with no children")
    else:
        result.ok("Structure", "No empty supervisors")

    # Well-formed check (no structural failures so far)
    structural_errors = sum(1 for c, _, ok in result.checks if c == "Structure" and not ok)
    if structural_errors == 0:
        result.ok("Structure", "Supervision tree well-formed")

    # --- Naming ---
    if all(a.get("name") for c in children for a in [c.get("agent", {})] if c.get("agent")):
        result.ok("Naming", "All agents named")

    seen: set[str] = set()
    has_dupe = False
    for name in agent_names:
        if name in seen:
            result.fail("Naming", f"Duplicate agent name: '{name}'")
            has_dupe = True
        seen.add(name)
    if not has_dupe:
        result.ok("Naming", "No duplicate names")

    name_conflict = False
    for name in agent_names:
        if name in supervisor_names:
            result.fail("Naming", f"Agent/supervisor name conflict: '{name}'")
            name_conflict = True
    if not name_conflict:
        result.ok("Naming", "No agent/supervisor name conflicts")

    # --- Configuration ---
    strategies_used = set()
    root_strategy = sup.get("strategy", "one_for_one").upper()
    strategies_used.add(root_strategy)

    def _collect_strategies(node: dict[str, Any]) -> None:
        if "supervisor" in node:
            s = node["supervisor"]
            strategies_used.add(s.get("strategy", "one_for_one").upper())
            for child in s.get("children", []):
                _collect_strategies(child)

    for child in children:
        _collect_strategies(child)

    if strategies_used <= _VALID_STRATEGIES:
        strat_list = ", ".join(sorted(strategies_used))
        result.ok("Configuration", f"Strategies valid ({strat_list})")

    # Check if any config-level failures were already recorded for backoff
    backoff_errors = sum(1 for _, msg, ok in result.checks if "backoff" in msg.lower() and not ok)
    if backoff_errors == 0:
        result.ok("Configuration", "Backoff policies valid")

    # Transport
    transport_cfg = config.get("transport", {})
    if transport_cfg:
        transport_type = transport_cfg.get("type", "in_process")
        if transport_type in _VALID_TRANSPORTS:
            result.ok("Configuration", f"Transport config valid — {transport_type}")
        else:
            result.fail("Configuration", f"Invalid transport type: '{transport_type}'")
    else:
        result.ok("Configuration", "Transport config valid — in_process")

    return result


# ---------------------------------------------------------------------------
# Rich tree builder
# ---------------------------------------------------------------------------


def _build_rich_tree(config: dict[str, Any]) -> Tree:
    """Build a Rich Tree with inline supervisor policies and agent metadata."""
    sup = config.get("supervision", config.get("supervisor", {}))
    root_name = sup.get("name", "root")
    strategy = sup.get("strategy", "ONE_FOR_ONE").upper()
    max_restarts = sup.get("max_restarts", 3)
    restart_window = sup.get("restart_window", 60.0)
    backoff = sup.get("backoff", "CONSTANT").upper()

    root_label = (
        f"[bold cyan]{root_name}[/bold cyan] [cyan]{strategy}[/cyan]  "
        f"[dim]restarts: {max_restarts}/{restart_window}s  backoff: {backoff.lower()}[/dim]"
    )
    tree = Tree(root_label)

    def _add_children(parent: Tree, children: list[dict[str, Any]]) -> None:
        for child in children:
            if "supervisor" in child:
                s = child["supervisor"]
                name = s.get("name", "?")
                strat = s.get("strategy", "ONE_FOR_ONE").upper()
                mr = s.get("max_restarts", 3)
                rw = s.get("restart_window", 60.0)
                bo = s.get("backoff", "CONSTANT").upper()

                label = (
                    f"[bold cyan]{name}[/bold cyan] [cyan]{strat}[/cyan]  "
                    f"[dim]restarts: {mr}/{rw}s  backoff: {bo.lower()}[/dim]"
                )
                branch = parent.add(label)
                _add_children(branch, s.get("children", []))

            elif "agent" in child:
                a = child["agent"]
                name = a.get("name", "?")
                agent_type = a.get("type", "?")
                label = f"[green]{name}[/green]  [dim]{agent_type}[/dim]"
                if "process" in a:
                    label += f"  [yellow]@{a['process']}[/yellow]"
                parent.add(label)

    _add_children(tree, sup.get("children", []))
    return tree


def _build_summary(config: dict[str, Any]) -> str:
    """Build a one-line summary footer for a topology."""
    sup = config.get("supervision", config.get("supervisor", {}))
    agent_count = _count_agents(sup)
    sup_count = _count_supervisors(sup)

    transport_cfg = config.get("transport", {})
    transport_type = transport_cfg.get("type", "in_process")
    transport_detail = f"[magenta]{transport_type}[/magenta]"

    if transport_type == "nats":
        servers = transport_cfg.get("servers", "nats://localhost:4222")
        transport_detail += f"  [dim]{servers}[/dim]"
        if transport_cfg.get("jetstream"):
            transport_detail += "  [dim]jetstream[/dim]"
    elif transport_type == "zmq":
        pub = transport_cfg.get("pub_addr", "")
        if pub:
            transport_detail += f"  [dim]{pub}[/dim]"

    # Plugins
    plugins_cfg = config.get("plugins", {})
    plugin_names: list[str] = []
    for section_name in ("model_providers", "exporters", "observability"):
        for p in plugins_cfg.get(section_name, []):
            ptype = p.get("type", "")
            short = ptype.rpartition(".")[2].replace("Provider", "").replace("Exporter", "").lower()
            if short:
                plugin_names.append(short)
    if plugins_cfg.get("state"):
        st = plugins_cfg["state"]
        short = st.get("type", "").rpartition(".")[2].replace("StateStore", "").lower()
        if short:
            plugin_names.append(short)

    # Count processes
    processes: set[str] = set()

    def _collect_processes(node: dict[str, Any]) -> None:
        if "supervisor" in node:
            for child in node["supervisor"].get("children", []):
                _collect_processes(child)
        elif "agent" in node:
            p = node["agent"].get("process")
            if p:
                processes.add(p)

    for child in sup.get("children", []):
        _collect_processes(child)

    lines = [f"  Transport   {transport_detail}"]
    if plugin_names:
        lines.append(f"  Plugins     [magenta]{'  '.join(plugin_names)}[/magenta]")
    topo_parts = [f"{agent_count} agents", f"{sup_count} supervisors"]
    if processes:
        topo_parts.append(f"{len(processes)} processes")
    lines.append(f"  Topology    [dim]{'  ·  '.join(topo_parts)}[/dim]")

    return "\n".join(lines)


def _count_agents(node: dict[str, Any]) -> int:
    """Count agents in a supervision config."""
    count = 0
    for child in node.get("children", []):
        if "agent" in child:
            count += 1
        elif "supervisor" in child:
            count += _count_agents(child["supervisor"])
    return count


def _count_supervisors(node: dict[str, Any]) -> int:
    """Count supervisors in a supervision config (including root)."""
    count = 1
    for child in node.get("children", []):
        if "supervisor" in child:
            count += _count_supervisors(child["supervisor"])
    return count


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def _flatten_topology(config: dict[str, Any]) -> dict[str, str]:
    """Flatten a topology config into semantic key-value pairs for diffing."""
    flat: dict[str, str] = {}
    sup = config.get("supervision", config.get("supervisor", {}))

    def _flatten_node(node: dict[str, Any], path: str) -> None:
        if "supervisor" in node:
            s = node["supervisor"]
            name = s.get("name", "?")
            p = f"{path}/{name}"
            flat[f"{p}/@type"] = "supervisor"
            flat[f"{p}/@strategy"] = s.get("strategy", "ONE_FOR_ONE").upper()
            flat[f"{p}/@max_restarts"] = str(s.get("max_restarts", 3))
            flat[f"{p}/@backoff"] = s.get("backoff", "CONSTANT").upper()
            for child in s.get("children", []):
                _flatten_node(child, p)
        elif "agent" in node:
            a = node["agent"]
            name = a.get("name", "?")
            p = f"{path}/{name}"
            flat[f"{p}/@type"] = "agent"
            flat[f"{p}/@class"] = a.get("type", "?")
            if "process" in a:
                flat[f"{p}/@process"] = a["process"]

    root_name = sup.get("name", "root")
    flat[f"/{root_name}/@type"] = "supervisor"
    flat[f"/{root_name}/@strategy"] = sup.get("strategy", "ONE_FOR_ONE").upper()
    flat[f"/{root_name}/@max_restarts"] = str(sup.get("max_restarts", 3))

    for child in sup.get("children", []):
        _flatten_node(child, f"/{root_name}")

    transport_cfg = config.get("transport", {})
    if transport_cfg:
        flat["transport/@type"] = transport_cfg.get("type", "in_process")
        for k, v in transport_cfg.items():
            if k != "type":
                flat[f"transport/@{k}"] = str(v)

    plugins_cfg = config.get("plugins", {})
    for sect_name, sect_val in plugins_cfg.items():
        if isinstance(sect_val, list):
            for i, p in enumerate(sect_val):
                flat[f"plugins/{sect_name}[{i}]/@type"] = p.get("type", "?")
        elif isinstance(sect_val, dict):
            flat[f"plugins/{sect_name}/@type"] = sect_val.get("type", "?")

    return flat


def _categorize_key(key: str) -> str:
    """Map a flat key to its diff display category."""
    if key.startswith("transport/"):
        return "Transport"
    if key.startswith("plugins/"):
        return "Plugins"
    return "Supervision"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@topology_app.command("validate")
def topology_validate(
    path: str = typer.Argument(help="Path to topology YAML file"),
) -> None:
    """Validate a topology YAML file."""
    topology_path = Path(path)
    if not topology_path.exists():
        err_console.print(f"[red]Error:[/red] File '{path}' not found.")
        raise typer.Exit(1)

    try:
        config = yaml.safe_load(topology_path.read_text())
    except yaml.YAMLError as exc:
        err_console.print(f"[red]YAML parse error:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"\n  Validating [cyan]{path}[/cyan]")

    result = _validate_topology(config)
    result.print()

    if result.passed:
        sup = config.get("supervision", config.get("supervisor", {}))
        transport = config.get("transport", {}).get("type", "in_process")
        console.print(
            f"\n  [green]✔ Valid[/green]  "
            f"[dim]{_count_agents(sup)} agents · "
            f"{_count_supervisors(sup)} supervisors · "
            f"{transport}[/dim]\n"
        )
    else:
        console.print(f"\n  [red]{result.error_count} errors found[/red]\n")
        raise typer.Exit(1)


@topology_app.command("show")
def topology_show(
    path: str = typer.Argument(help="Path to topology YAML file"),
) -> None:
    """Visualize a topology as a Rich tree."""
    topology_path = Path(path)
    if not topology_path.exists():
        err_console.print(f"[red]Error:[/red] File '{path}' not found.")
        raise typer.Exit(1)

    config = yaml.safe_load(topology_path.read_text())

    console.print(f"\n  [bold]Agency Topology:[/bold] [cyan]{path}[/cyan]\n")
    tree = _build_rich_tree(config)
    console.print(tree)
    console.print()
    console.print(Rule(style="dim"))
    console.print()
    console.print(_build_summary(config))
    console.print()


@topology_app.command("diff")
def topology_diff(
    file_a: str = typer.Argument(help="First topology YAML file"),
    file_b: str = typer.Argument(help="Second topology YAML file"),
) -> None:
    """Show differences between two topology files."""
    path_a = Path(file_a)
    path_b = Path(file_b)

    for p, label in [(path_a, file_a), (path_b, file_b)]:
        if not p.exists():
            err_console.print(f"[red]Error:[/red] File '{label}' not found.")
            raise typer.Exit(1)

    config_a = yaml.safe_load(path_a.read_text())
    config_b = yaml.safe_load(path_b.read_text())

    flat_a = _flatten_topology(config_a)
    flat_b = _flatten_topology(config_b)

    all_keys = sorted(set(flat_a.keys()) | set(flat_b.keys()))

    # Group diffs by category
    added = 0
    changed = 0
    removed = 0
    current_category = ""

    console.print(f"\n  [bold]Diff:[/bold] [cyan]{file_a}[/cyan] → [cyan]{file_b}[/cyan]\n")

    has_diff = False
    for key in all_keys:
        val_a = flat_a.get(key)
        val_b = flat_b.get(key)
        if val_a == val_b:
            continue

        has_diff = True
        cat = _categorize_key(key)
        if cat != current_category:
            section(cat)
            current_category = cat

        # Strip category prefix from display key for cleaner output
        display_key = key

        if val_a is None:
            console.print(f"    [green]+[/green] {display_key:<35} [green]{val_b}[/green]")
            added += 1
        elif val_b is None:
            console.print(f"    [red]-[/red] {display_key:<35} [red]{val_a}[/red]")
            removed += 1
        else:
            console.print(
                f"    [yellow]~[/yellow] {display_key:<35} "
                f"[dim]{val_a}[/dim] → [yellow]{val_b}[/yellow]"
            )
            changed += 1

    if has_diff:
        parts = []
        if changed:
            parts.append(f"[yellow]{changed} changed[/yellow]")
        if added:
            parts.append(f"[green]{added} added[/green]")
        if removed:
            parts.append(f"[red]{removed} removed[/red]")
        console.print(f"\n  {' · '.join(parts)}\n")
    else:
        console.print("  [green]No differences found.[/green]\n")
