"""M3.1 — Bootstrap & Upgrade CLI testable criteria.

Tests validate that the Typer+Rich CLI scaffolds projects, runs topologies,
manages state, and switches transports via flags.
"""

import asyncio
import os
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from agency.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# agency version
# ---------------------------------------------------------------------------


def test_version():
    """agency version prints version info."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


# ---------------------------------------------------------------------------
# agency init
# ---------------------------------------------------------------------------


def test_init_scaffolds_project():
    """agency init creates project directory with expected files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(app, ["init", "my_project", "--dir", tmpdir])
        assert result.exit_code == 0

        project_dir = Path(tmpdir) / "my_project"
        assert project_dir.exists()
        assert (project_dir / "pyproject.toml").exists()
        assert (project_dir / "topology.yaml").exists()
        assert (project_dir / "agents.py").exists()
        assert (project_dir / "run.py").exists()
        assert (project_dir / "README.md").exists()


def test_init_pyproject_has_agency_dep():
    """Scaffolded pyproject.toml includes python-agency dependency."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner.invoke(app, ["init", "dep_test", "--dir", tmpdir])
        content = (Path(tmpdir) / "dep_test" / "pyproject.toml").read_text()
        assert "python-agency" in content


def test_init_topology_is_valid_yaml():
    """Scaffolded topology.yaml is valid YAML with supervision section."""
    import yaml

    with tempfile.TemporaryDirectory() as tmpdir:
        runner.invoke(app, ["init", "yaml_test", "--dir", tmpdir])
        content = (Path(tmpdir) / "yaml_test" / "topology.yaml").read_text()
        config = yaml.safe_load(content)
        assert "supervision" in config
        assert config["supervision"]["name"] == "root"


def test_init_agents_contains_agent_class():
    """Scaffolded agents.py contains an AgentProcess subclass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner.invoke(app, ["init", "agent_test", "--dir", tmpdir])
        content = (Path(tmpdir) / "agent_test" / "agents.py").read_text()
        assert "class GreeterAgent(AgentProcess)" in content
        assert "async def handle" in content


def test_init_rejects_existing_directory():
    """agency init refuses to overwrite an existing directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create the directory first
        (Path(tmpdir) / "existing").mkdir()
        result = runner.invoke(app, ["init", "existing", "--dir", tmpdir])
        assert result.exit_code == 1


def test_init_run_script_is_functional():
    """Scaffolded run.py contains runnable structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner.invoke(app, ["init", "func_test", "--dir", tmpdir])
        content = (Path(tmpdir) / "func_test" / "run.py").read_text()
        assert "asyncio.run(main())" in content
        assert "Runtime.from_config" in content


# ---------------------------------------------------------------------------
# agency run
# ---------------------------------------------------------------------------


def test_run_missing_topology():
    """agency run with nonexistent topology file shows error."""
    result = runner.invoke(app, ["run", "--topology", "/nonexistent/topology.yaml"])
    assert result.exit_code == 1


def test_run_help():
    """agency run --help shows transport and process options."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--topology" in result.output
    assert "--transport" in result.output
    assert "--process" in result.output


# ---------------------------------------------------------------------------
# agency state
# ---------------------------------------------------------------------------


def test_state_list_no_db():
    """agency state list with no database shows friendly message."""
    result = runner.invoke(app, ["state", "list", "--db", "/nonexistent/state.db"])
    assert result.exit_code == 0


def test_state_list_shows_agents():
    """agency state list shows agents in a Rich table."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        import asyncio

        from agency.plugins.sqlite_store import SQLiteStateStore

        store = SQLiteStateStore(db_path)
        asyncio.run(store.set("agent_a", {"count": 42}))
        asyncio.run(store.set("agent_b", {"step": 3, "data": "hello"}))
        asyncio.run(store.close())

        result = runner.invoke(app, ["state", "list", "--db", db_path])
        assert result.exit_code == 0
        assert "agent_a" in result.output
        assert "agent_b" in result.output
        assert "42" in result.output
    finally:
        os.unlink(db_path)


def test_state_clear_specific_agent():
    """agency state clear <name> removes state for that agent."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        import asyncio

        from agency.plugins.sqlite_store import SQLiteStateStore

        store = SQLiteStateStore(db_path)
        asyncio.run(store.set("agent_a", {"v": 1}))
        asyncio.run(store.set("agent_b", {"v": 2}))
        asyncio.run(store.close())

        result = runner.invoke(app, ["state", "clear", "agent_a", "--db", db_path, "--force"])
        assert result.exit_code == 0
        assert "agent_a" in result.output

        # Verify agent_a removed, agent_b remains
        store = SQLiteStateStore(db_path)
        assert asyncio.run(store.get("agent_a")) is None
        assert asyncio.run(store.get("agent_b")) == {"v": 2}
        asyncio.run(store.close())
    finally:
        os.unlink(db_path)


def test_state_clear_all():
    """agency state clear (no name) removes all agent states."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        import asyncio

        from agency.plugins.sqlite_store import SQLiteStateStore

        store = SQLiteStateStore(db_path)
        asyncio.run(store.set("agent_a", {"v": 1}))
        asyncio.run(store.set("agent_b", {"v": 2}))
        asyncio.run(store.close())

        result = runner.invoke(app, ["state", "clear", "--db", db_path, "--force"])
        assert result.exit_code == 0

        store = SQLiteStateStore(db_path)
        assert asyncio.run(store.list_agents()) == []
        asyncio.run(store.close())
    finally:
        os.unlink(db_path)


def test_state_clear_nonexistent_agent():
    """agency state clear for unknown agent shows message."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        from agency.plugins.sqlite_store import SQLiteStateStore

        store = SQLiteStateStore(db_path)
        asyncio.run(store.close())

        result = runner.invoke(app, ["state", "clear", "ghost", "--db", db_path, "--force"])
        assert result.exit_code == 0
    finally:
        os.unlink(db_path)


# ---------------------------------------------------------------------------
# Transport switching (via CLI flags)
# ---------------------------------------------------------------------------


def test_run_transport_override_flag():
    """--transport flag is accepted and shown in help."""
    result = runner.invoke(app, ["run", "--help"])
    assert "--transport" in result.output
    # Verify nats-url is also available
    assert "--nats-url" in result.output


# ---------------------------------------------------------------------------
# F09 — CLI hardening
# ---------------------------------------------------------------------------


def test_init_rejects_invalid_identifier():
    """agency init rejects names that are not valid Python identifiers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(app, ["init", "my-project", "--dir", tmpdir])
        assert result.exit_code == 1
        assert "not a valid Python identifier" in result.output

        result = runner.invoke(app, ["init", "123start", "--dir", tmpdir])
        assert result.exit_code == 1

        result = runner.invoke(app, ["init", "has space", "--dir", tmpdir])
        assert result.exit_code == 1


def test_topology_validate_bad_yaml():
    """topology validate reports YAML parse errors cleanly."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(":\n  - bad: [unclosed\n")
        path = f.name

    try:
        result = runner.invoke(app, ["topology", "validate", path])
        assert result.exit_code == 1
    finally:
        os.unlink(path)


def test_topology_validate_no_supervision():
    """topology validate reports missing supervision section."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write("transport:\n  type: in_process\n")
        path = f.name

    try:
        result = runner.invoke(app, ["topology", "validate", path])
        assert result.exit_code == 1
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------


def test_python_m_agency():
    """python -m agency works as entry point."""
    import subprocess

    venv_python = str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "python")
    result = subprocess.run(
        [venv_python, "-m", "agency", "version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout
