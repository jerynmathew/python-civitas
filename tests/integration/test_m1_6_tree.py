"""M1.6 — Supervision Tree testable criteria.

Tests YAML config loading and ASCII tree output.
"""

import tempfile
from pathlib import Path

from civitas import AgentProcess, Runtime, Supervisor
from civitas.messages import Message

# ------------------------------------------------------------------
# Test agents
# ------------------------------------------------------------------


class WorkerAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        return self.reply({"worker": self.name})


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _write_yaml(content: str) -> Path:
    """Write YAML to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


BASIC_YAML = """\
supervision:
  name: root
  strategy: one_for_one
  max_restarts: 3
  restart_window: 60.0
  children:
    - agent: { type: WorkerAgent, name: worker_a }
    - agent: { type: WorkerAgent, name: worker_b }
"""

NESTED_YAML = """\
supervision:
  name: root
  strategy: one_for_one
  children:
    - supervisor:
        name: group_sup
        strategy: one_for_all
        max_restarts: 5
        restart_window: 30.0
        backoff: exponential
        children:
          - agent: { type: WorkerAgent, name: worker_1 }
          - agent: { type: WorkerAgent, name: worker_2 }
    - agent: { type: WorkerAgent, name: worker_3 }
"""

CLASSES = {"WorkerAgent": WorkerAgent}


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


async def test_from_config_basic():
    """Runtime.from_config() parses a basic YAML topology."""
    path = _write_yaml(BASIC_YAML)
    runtime = Runtime.from_config(path, agent_classes=CLASSES)

    await runtime.start()
    try:
        r = await runtime.ask("worker_a", {})
        assert r.payload["worker"] == "worker_a"
        r = await runtime.ask("worker_b", {})
        assert r.payload["worker"] == "worker_b"
    finally:
        await runtime.stop()


async def test_from_config_nested_supervisors():
    """YAML with nested supervisors produces a correct tree."""
    path = _write_yaml(NESTED_YAML)
    runtime = Runtime.from_config(path, agent_classes=CLASSES)

    await runtime.start()
    try:
        # All three workers should be reachable
        for name in ("worker_1", "worker_2", "worker_3"):
            r = await runtime.ask(name, {})
            assert r.payload["worker"] == name
    finally:
        await runtime.stop()


async def test_yaml_and_dsl_produce_identical_behaviour():
    """Python DSL and YAML produce identical runtime behaviour."""
    # DSL version
    dsl_runtime = Runtime(
        supervisor=Supervisor(
            "root",
            strategy="ONE_FOR_ONE",
            max_restarts=3,
            restart_window=60.0,
            children=[WorkerAgent("worker_a"), WorkerAgent("worker_b")],
        )
    )

    # YAML version
    path = _write_yaml(BASIC_YAML)
    yaml_runtime = Runtime.from_config(path, agent_classes=CLASSES)

    # Start both
    await dsl_runtime.start()
    await yaml_runtime.start()

    try:
        # Both should route messages identically
        dsl_r = await dsl_runtime.ask("worker_a", {"q": "test"})
        yaml_r = await yaml_runtime.ask("worker_a", {"q": "test"})
        assert dsl_r.payload == yaml_r.payload

        # Both should have the same tree structure
        dsl_tree = dsl_runtime.print_tree()
        yaml_tree = yaml_runtime.print_tree()
        # Both trees should mention the same agents
        assert "worker_a" in dsl_tree and "worker_a" in yaml_tree
        assert "worker_b" in dsl_tree and "worker_b" in yaml_tree
    finally:
        await dsl_runtime.stop()
        await yaml_runtime.stop()


async def test_print_tree_ascii():
    """print_tree() returns a readable ASCII tree."""
    path = _write_yaml(NESTED_YAML)
    runtime = Runtime.from_config(path, agent_classes=CLASSES)

    tree = runtime.print_tree()

    # Verify structure
    assert "[sup] root" in tree
    assert "[sup] group_sup" in tree
    assert "worker_1" in tree
    assert "worker_2" in tree
    assert "worker_3" in tree
    assert "ONE_FOR_ALL" in tree  # group_sup strategy


async def test_print_tree_shows_agent_status():
    """print_tree() shows agent status after start."""
    runtime = Runtime(supervisor=Supervisor("root", children=[WorkerAgent("w1")]))
    await runtime.start()
    try:
        tree = runtime.print_tree()
        assert "RUNNING" in tree
    finally:
        await runtime.stop()


async def test_from_config_supervisor_settings():
    """YAML supervisor settings (strategy, backoff, etc.) are applied."""
    path = _write_yaml(NESTED_YAML)
    runtime = Runtime.from_config(path, agent_classes=CLASSES)

    root = runtime._root_supervisor
    assert root.name == "root"
    assert root.strategy.value == "ONE_FOR_ONE"

    group_sup = root.children[0]
    assert isinstance(group_sup, Supervisor)
    assert group_sup.name == "group_sup"
    assert group_sup.strategy.value == "ONE_FOR_ALL"
    assert group_sup.max_restarts == 5
    assert group_sup.restart_window == 30.0
    assert group_sup.backoff.value == "EXPONENTIAL"
