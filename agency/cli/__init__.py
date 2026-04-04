"""Agency CLI — command-line interface for the Agency runtime.

Built with Typer + Rich (DR-011). See docs/08-CLI-Design.md for the
full design specification.

Package structure:
    app.py       — shared Typer app, consoles, output helpers
    init.py      — agency init
    run.py       — agency run
    state.py     — agency state list|clear
    topology.py  — agency topology validate|show|diff
    deploy.py    — agency deploy (M2.7)
    version.py   — agency version
    _templates/  — scaffolding templates
"""

from __future__ import annotations

# F09-8: guard dashboard import — it requires optional dependencies (rich Live).
# If the import fails, the rest of the CLI still loads normally.
try:
    import agency.cli.dashboard  # noqa: F401
except ImportError:
    pass

# Register all subcommands by importing the modules that decorate them.
# Each module adds its commands to the shared `app` instance.
import agency.cli.init  # noqa: F401
import agency.cli.run  # noqa: F401
import agency.cli.version  # noqa: F401
from agency.cli.app import app
from agency.cli.deploy import deploy_app

# Register subcommand groups
from agency.cli.state import state_app
from agency.cli.topology import topology_app

app.add_typer(state_app, name="state")
app.add_typer(topology_app, name="topology")
app.add_typer(deploy_app, name="deploy")


def main() -> None:
    """CLI entry point — called by ``[project.scripts] agency``."""
    app()
