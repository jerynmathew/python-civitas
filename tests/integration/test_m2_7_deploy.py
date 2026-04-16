"""M2.7 — Docker Containerized Deployment testable criteria.

Tests validate that `civitas deploy docker-compose` generates valid
deployment artifacts from topology YAML files.
"""

import tempfile
from pathlib import Path

import yaml
from typer.testing import CliRunner

from civitas.cli import app
from civitas.cli.deploy import _collect_processes, _generate_docker_compose, _generate_env_file

runner = CliRunner()

_NATS_TOPOLOGY = {
    "transport": {"type": "nats", "servers": "nats://localhost:4222", "jetstream": True},
    "supervision": {
        "name": "root",
        "strategy": "one_for_one",
        "children": [
            {"agent": {"type": "app.Orchestrator", "name": "orchestrator"}},
            {
                "supervisor": {
                    "name": "workers_sup",
                    "strategy": "one_for_one",
                    "children": [
                        {
                            "agent": {
                                "type": "app.Worker",
                                "name": "worker_a",
                                "process": "worker-1",
                            }
                        },
                        {
                            "agent": {
                                "type": "app.Worker",
                                "name": "worker_b",
                                "process": "worker-1",
                            }
                        },
                        {
                            "agent": {
                                "type": "app.Analyzer",
                                "name": "analyzer",
                                "process": "worker-2",
                            }
                        },
                    ],
                }
            },
        ],
    },
    "plugins": {
        "models": [{"type": "civitas.plugins.anthropic.AnthropicProvider"}],
        "exporters": [{"type": "civitas.plugins.otel.OTELExporter"}],
    },
}

_SIMPLE_TOPOLOGY = {
    "supervision": {
        "name": "root",
        "strategy": "one_for_one",
        "children": [
            {"agent": {"type": "app.Agent", "name": "agent_a"}},
        ],
    },
}


# ---------------------------------------------------------------------------
# Process collection
# ---------------------------------------------------------------------------


def test_collect_processes_groups_by_affinity():
    """Agents are grouped by their process affinity."""
    processes = _collect_processes(_NATS_TOPOLOGY)
    assert "supervisor" in processes
    assert "worker-1" in processes
    assert "worker-2" in processes
    assert len(processes["worker-1"]) == 2
    assert len(processes["worker-2"]) == 1


def test_collect_processes_default_supervisor():
    """Agents without process key default to 'supervisor'."""
    processes = _collect_processes(_NATS_TOPOLOGY)
    supervisor_agents = [a["name"] for a in processes["supervisor"]]
    assert "orchestrator" in supervisor_agents


# ---------------------------------------------------------------------------
# Docker Compose generation
# ---------------------------------------------------------------------------


def test_generates_valid_yaml():
    """Generated docker-compose.yml is valid YAML."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    assert "services" in config


def test_generates_nats_service():
    """NATS service is included when transport is nats."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    assert "nats" in config["services"]
    assert config["services"]["nats"]["image"] == "nats:latest"


def test_generates_nats_healthcheck():
    """NATS service has a healthcheck."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    assert "healthcheck" in config["services"]["nats"]


def test_generates_supervisor_service():
    """Supervisor service is generated with correct command."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    assert "supervisor" in config["services"]
    assert "--topology" in config["services"]["supervisor"]["command"]


def test_generates_worker_services():
    """Worker services are generated for each process group."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    assert "worker-worker-1" in config["services"]
    assert "worker-worker-2" in config["services"]


def test_worker_has_process_flag():
    """Worker command includes --process flag."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    cmd = config["services"]["worker-worker-1"]["command"]
    assert "--process" in cmd
    assert "worker-1" in cmd


def test_worker_has_agent_labels():
    """Worker services have labels listing their agents."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    labels = config["services"]["worker-worker-1"]["labels"]
    assert "civitas.agents" in labels
    assert "worker_a" in labels["civitas.agents"]


def test_nats_dependency():
    """Supervisor and workers depend on NATS being healthy."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    assert "nats" in config["services"]["supervisor"]["depends_on"]
    assert "nats" in config["services"]["worker-worker-1"]["depends_on"]


def test_no_nats_for_inprocess():
    """In-process transport does not generate NATS service."""
    output = _generate_docker_compose(_SIMPLE_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    assert "nats" not in config["services"]


def test_jetstream_flag():
    """JetStream flag is passed to NATS command when enabled."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    nats = config["services"]["nats"]
    assert nats.get("command") == "--jetstream"


def test_restart_policy():
    """All services have restart: unless-stopped."""
    output = _generate_docker_compose(_NATS_TOPOLOGY, "topology.yaml")
    config = yaml.safe_load(output)
    for name, svc in config["services"].items():
        assert svc.get("restart") == "unless-stopped", f"{name} missing restart policy"


# ---------------------------------------------------------------------------
# .env generation
# ---------------------------------------------------------------------------


def test_env_file_includes_serializer():
    """Generated .env includes AGENCY_SERIALIZER."""
    env = _generate_env_file(_NATS_TOPOLOGY)
    assert "AGENCY_SERIALIZER" in env


def test_env_file_includes_api_keys():
    """Generated .env includes placeholders for configured providers."""
    env = _generate_env_file(_NATS_TOPOLOGY)
    assert "ANTHROPIC_API_KEY" in env
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in env


def test_env_file_no_extra_keys_for_simple():
    """Simple topology without plugins has minimal .env."""
    env = _generate_env_file(_SIMPLE_TOPOLOGY)
    assert "ANTHROPIC_API_KEY" not in env


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def test_deploy_command_generates_files():
    """civitas deploy docker-compose creates all expected files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        topo_path = Path(tmpdir) / "topology.yaml"
        topo_path.write_text(yaml.dump(_NATS_TOPOLOGY))

        out_dir = Path(tmpdir) / "deploy"
        result = runner.invoke(
            app,
            [
                "deploy",
                "docker-compose",
                "--topology",
                str(topo_path),
                "--output",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0
        assert (out_dir / "docker-compose.yml").exists()
        assert (out_dir / "Dockerfile").exists()
        assert (out_dir / ".env").exists()
        assert (out_dir / "topology.yaml").exists()


def test_deploy_command_missing_topology():
    """Missing topology file shows error."""
    result = runner.invoke(
        app,
        [
            "deploy",
            "docker-compose",
            "--topology",
            "/nonexistent.yaml",
        ],
    )
    assert result.exit_code == 1


def test_deploy_dockerfile_content():
    """Generated Dockerfile uses python:3.12-slim and installs civitas."""
    with tempfile.TemporaryDirectory() as tmpdir:
        topo_path = Path(tmpdir) / "topology.yaml"
        topo_path.write_text(yaml.dump(_SIMPLE_TOPOLOGY))

        out_dir = Path(tmpdir) / "deploy"
        runner.invoke(
            app,
            [
                "deploy",
                "docker-compose",
                "--topology",
                str(topo_path),
                "--output",
                str(out_dir),
            ],
        )
        dockerfile = (out_dir / "Dockerfile").read_text()
        assert "python:3.12-slim" in dockerfile
        assert "civitas" in dockerfile
