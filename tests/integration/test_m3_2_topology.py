"""M3.2 — Declarative Topology Format testable criteria.

Tests validate that topology validate, show, and diff commands produce
correct Rich-formatted output with proper grouping and styling.
"""

import tempfile
from pathlib import Path

import yaml
from typer.testing import CliRunner

from agency.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures — reusable YAML configs
# ---------------------------------------------------------------------------

_VALID_TOPOLOGY = {
    "supervision": {
        "name": "root",
        "strategy": "one_for_one",
        "max_restarts": 3,
        "restart_window": 60.0,
        "children": [
            {
                "supervisor": {
                    "name": "workers",
                    "strategy": "one_for_all",
                    "max_restarts": 5,
                    "restart_window": 30.0,
                    "backoff": "exponential",
                    "children": [
                        {"agent": {"type": "app.Worker", "name": "worker_a"}},
                        {"agent": {"type": "app.Worker", "name": "worker_b"}},
                    ],
                }
            },
            {"agent": {"type": "app.Router", "name": "router"}},
        ],
    },
    "transport": {"type": "nats", "servers": "nats://prod:4222", "jetstream": True},
}

_STAGING_TOPOLOGY = {
    "supervision": {
        "name": "root",
        "strategy": "one_for_one",
        "max_restarts": 3,
        "children": [
            {"agent": {"type": "app.Worker", "name": "worker_a"}},
            {"agent": {"type": "app.Router", "name": "router"}},
        ],
    },
}

_INVALID_TOPOLOGY_DUPE = {
    "supervision": {
        "name": "root",
        "strategy": "one_for_one",
        "children": [
            {"agent": {"type": "app.A", "name": "worker"}},
            {"agent": {"type": "app.B", "name": "worker"}},
        ],
    },
}

_INVALID_TOPOLOGY_STRATEGY = {
    "supervision": {
        "name": "root",
        "strategy": "round_robin",
        "children": [
            {"agent": {"type": "app.A", "name": "a"}},
        ],
    },
}

_INVALID_TOPOLOGY_EMPTY_SUP = {
    "supervision": {
        "name": "root",
        "strategy": "one_for_one",
        "children": [
            {"supervisor": {"name": "empty_sup", "strategy": "one_for_one", "children": []}},
        ],
    },
}


def _write_yaml(config: dict, tmpdir: str, name: str = "topology.yaml") -> str:
    """Write a config dict to a YAML file and return the path."""
    path = Path(tmpdir) / name
    path.write_text(yaml.dump(config))
    return str(path)


# ---------------------------------------------------------------------------
# agency topology validate
# ---------------------------------------------------------------------------


def test_validate_valid_topology():
    """Valid topology shows all checkmarks and passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_VALID_TOPOLOGY, tmpdir)
        result = runner.invoke(app, ["topology", "validate", path])
        assert result.exit_code == 0
        assert "Valid" in result.output


def test_validate_grouped_categories():
    """Validation output contains grouped categories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_VALID_TOPOLOGY, tmpdir)
        result = runner.invoke(app, ["topology", "validate", path])
        assert "Structure" in result.output
        assert "Naming" in result.output
        assert "Configuration" in result.output


def test_validate_shows_agent_count():
    """Validation summary shows correct agent and supervisor counts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_VALID_TOPOLOGY, tmpdir)
        result = runner.invoke(app, ["topology", "validate", path])
        assert "3 agents" in result.output
        assert "2 supervisors" in result.output


def test_validate_duplicate_agent_name():
    """Duplicate agent names are caught and reported."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_INVALID_TOPOLOGY_DUPE, tmpdir)
        result = runner.invoke(app, ["topology", "validate", path])
        assert result.exit_code == 1
        assert "Duplicate agent name" in result.output or "duplicate" in result.output.lower()


def test_validate_invalid_strategy():
    """Invalid strategy is caught and reported."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_INVALID_TOPOLOGY_STRATEGY, tmpdir)
        result = runner.invoke(app, ["topology", "validate", path])
        assert result.exit_code == 1


def test_validate_empty_supervisor():
    """Empty supervisor (no children) is caught."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_INVALID_TOPOLOGY_EMPTY_SUP, tmpdir)
        result = runner.invoke(app, ["topology", "validate", path])
        assert result.exit_code == 1


def test_validate_missing_file():
    """Nonexistent file shows error."""
    result = runner.invoke(app, ["topology", "validate", "/nonexistent.yaml"])
    assert result.exit_code == 1


def test_validate_transport_type():
    """Transport validation shows correct type in output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_VALID_TOPOLOGY, tmpdir)
        result = runner.invoke(app, ["topology", "validate", path])
        assert "nats" in result.output


# ---------------------------------------------------------------------------
# agency topology show
# ---------------------------------------------------------------------------


def test_show_displays_tree():
    """Show command renders a tree with supervisor and agent names."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_VALID_TOPOLOGY, tmpdir)
        result = runner.invoke(app, ["topology", "show", path])
        assert result.exit_code == 0
        assert "root" in result.output
        assert "workers" in result.output
        assert "worker_a" in result.output
        assert "router" in result.output


def test_show_inline_supervisor_policies():
    """Show displays strategy, restart budget, and backoff inline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_VALID_TOPOLOGY, tmpdir)
        result = runner.invoke(app, ["topology", "show", path])
        assert "ONE_FOR_ONE" in result.output
        assert "ONE_FOR_ALL" in result.output
        assert "exponential" in result.output
        assert "5/30.0s" in result.output


def test_show_summary_footer():
    """Show displays transport and topology summary in footer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(_VALID_TOPOLOGY, tmpdir)
        result = runner.invoke(app, ["topology", "show", path])
        assert "Transport" in result.output
        assert "nats" in result.output
        assert "nats://prod:4222" in result.output
        assert "3 agents" in result.output


def test_show_process_affinity():
    """Agents with process affinity show @process tag."""
    config = {
        "supervision": {
            "name": "root",
            "strategy": "one_for_one",
            "children": [
                {"agent": {"type": "app.A", "name": "remote_agent", "process": "worker-1"}},
            ],
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_yaml(config, tmpdir)
        result = runner.invoke(app, ["topology", "show", path])
        assert "@worker-1" in result.output


def test_show_missing_file():
    """Nonexistent file shows error."""
    result = runner.invoke(app, ["topology", "show", "/nonexistent.yaml"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# agency topology diff
# ---------------------------------------------------------------------------


def test_diff_detects_changes():
    """Diff detects added, removed, and changed entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = _write_yaml(_STAGING_TOPOLOGY, tmpdir, "staging.yaml")
        path_b = _write_yaml(_VALID_TOPOLOGY, tmpdir, "prod.yaml")
        result = runner.invoke(app, ["topology", "diff", path_a, path_b])
        assert result.exit_code == 0
        assert "changed" in result.output or "added" in result.output


def test_diff_groups_by_section():
    """Diff output groups changes by Supervision, Transport, Plugins."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = _write_yaml(_STAGING_TOPOLOGY, tmpdir, "staging.yaml")
        path_b = _write_yaml(_VALID_TOPOLOGY, tmpdir, "prod.yaml")
        result = runner.invoke(app, ["topology", "diff", path_a, path_b])
        assert "Supervision" in result.output
        assert "Transport" in result.output


def test_diff_identical_files():
    """Diffing identical files shows no differences."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = _write_yaml(_VALID_TOPOLOGY, tmpdir, "a.yaml")
        path_b = _write_yaml(_VALID_TOPOLOGY, tmpdir, "b.yaml")
        result = runner.invoke(app, ["topology", "diff", path_a, path_b])
        assert result.exit_code == 0
        assert "No differences" in result.output


def test_diff_shows_change_indicators():
    """Diff uses ~ + - indicators for changed/added/removed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = _write_yaml(_STAGING_TOPOLOGY, tmpdir, "staging.yaml")
        path_b = _write_yaml(_VALID_TOPOLOGY, tmpdir, "prod.yaml")
        result = runner.invoke(app, ["topology", "diff", path_a, path_b])
        # At least one of these indicators should appear
        assert "~" in result.output or "+" in result.output or "-" in result.output


def test_diff_summary_line():
    """Diff ends with a summary count of changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = _write_yaml(_STAGING_TOPOLOGY, tmpdir, "staging.yaml")
        path_b = _write_yaml(_VALID_TOPOLOGY, tmpdir, "prod.yaml")
        result = runner.invoke(app, ["topology", "diff", path_a, path_b])
        assert "added" in result.output or "changed" in result.output or "removed" in result.output


def test_diff_missing_file():
    """Nonexistent file shows error."""
    result = runner.invoke(app, ["topology", "diff", "/nonexistent.yaml", "/also_nonexistent.yaml"])
    assert result.exit_code == 1
