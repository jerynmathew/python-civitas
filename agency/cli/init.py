"""agency init — scaffold a new Agency project."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from string import Template

import typer
from rich.panel import Panel

from agency.cli.app import app, console, err_console

_TEMPLATE_FILES = [
    ("pyproject.toml", "pyproject.toml.tmpl"),
    ("topology.yaml", "topology.yaml.tmpl"),
    ("agents.py", "agents.py.tmpl"),
    ("run.py", "run.py.tmpl"),
    ("README.md", "README.md.tmpl"),
]


def _load_template(name: str) -> Template:
    """Load a template file from the _templates package."""
    ref = resources.files("agency.cli._templates").joinpath(name)
    return Template(ref.read_text(encoding="utf-8"))


@app.command()
def init(
    name: str = typer.Argument(help="Project name (also the directory name)"),
    directory: str | None = typer.Option(None, "--dir", "-d", help="Parent directory"),
) -> None:
    """Scaffold a new Agency project."""
    parent = Path(directory) if directory else Path.cwd()
    project_dir = parent / name

    if project_dir.exists():
        err_console.print(f"[red]Error:[/red] Directory '{project_dir}' already exists.")
        raise typer.Exit(1)

    project_dir.mkdir(parents=True)

    for filename, tmpl_name in _TEMPLATE_FILES:
        tmpl = _load_template(tmpl_name)
        content = tmpl.substitute(project_name=name)
        (project_dir / filename).write_text(content)

    console.print(
        Panel.fit(
            f"[green]✔ Created {name}[/green]\n\n"
            f"  Next steps:\n"
            f"    cd {name}\n"
            f"    pip install -e .\n"
            f"    agency run\n",
            title="agency init",
            border_style="green",
        )
    )
