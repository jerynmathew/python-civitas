"""M2.3 — Plugin System testable criteria.

Tests validate that plugins can be:
- Loaded from YAML configuration without code imports
- Resolved via entrypoints, built-in names, or dotted import paths
- Configured with multiple providers/exporters simultaneously
- Custom user-written plugins loaded via dotted paths
- Clear error messages produced on load failure
"""

import os
import tempfile

import pytest

from civitas import AgentProcess, Runtime
from civitas.errors import CivitasError
from civitas.errors import PluginError as AgencyPluginError
from civitas.messages import Message
from civitas.plugins.loader import (
    PluginError,
    load_plugin,
    load_plugins_from_config,
    resolve_plugin_class,
)
from civitas.plugins.loader import (
    PluginError as LoaderPluginError,
)
from civitas.plugins.model import ModelResponse
from civitas.plugins.state import InMemoryStateStore
from civitas.plugins.tools import ToolRegistry

# ---------------------------------------------------------------------------
# Test plugins (simulating user-written custom plugins)
# ---------------------------------------------------------------------------


class MockModelProvider:
    """Custom model provider for testing plugin loading."""

    def __init__(self, model: str = "mock-v1", temperature: float = 0.7) -> None:
        self.model = model
        self.temperature = temperature

    async def chat(self, model=None, messages=None, tools=None):
        return ModelResponse(
            content="mock response",
            model=model or self.model,
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.0,
        )


class MockStateStore:
    """Custom state store for testing plugin loading."""

    def __init__(self, backend: str = "redis") -> None:
        self.backend = backend
        self._data: dict = {}

    async def get(self, agent_name):
        return self._data.get(agent_name)

    async def set(self, agent_name, state):
        self._data[agent_name] = state

    async def delete(self, agent_name):
        self._data.pop(agent_name, None)


class MockExporter:
    """Custom exporter for testing plugin loading."""

    def __init__(self, endpoint: str = "http://localhost:4317") -> None:
        self.endpoint = endpoint


# ---------------------------------------------------------------------------
# Plugin resolution tests
# ---------------------------------------------------------------------------


async def test_resolve_builtin_state_plugin():
    """Built-in plugin names resolve to correct classes."""
    cls = resolve_plugin_class("state", "in_memory")
    assert cls is InMemoryStateStore


async def test_resolve_dotted_import_path():
    """Dotted import paths resolve to the correct class."""
    cls = resolve_plugin_class(
        "model",
        "tests.integration.test_m2_3_plugins.MockModelProvider",
    )
    assert cls is MockModelProvider


async def test_resolve_unknown_plugin_raises():
    """Unknown plugin name produces PluginError with helpful message."""
    with pytest.raises(PluginError) as exc_info:
        resolve_plugin_class("model", "nonexistent_plugin")

    err = exc_info.value
    assert err.plugin_type == "model"
    assert err.name == "nonexistent_plugin"
    assert "Unknown plugin" in str(err)
    assert "pip install" in str(err)


async def test_resolve_bad_dotted_path_raises():
    """Invalid dotted import path produces clear error."""
    with pytest.raises(PluginError) as exc_info:
        resolve_plugin_class("model", "nonexistent.module.ClassName")

    assert "Cannot import module" in str(exc_info.value)


async def test_resolve_dotted_path_missing_class_raises():
    """Valid module but missing class produces clear error."""
    with pytest.raises(PluginError) as exc_info:
        resolve_plugin_class("model", "civitas.plugins.state.NonExistentClass")

    assert "has no attribute" in str(exc_info.value)


async def test_resolve_short_name_raises():
    """Single-word non-builtin name produces clear error."""
    with pytest.raises(PluginError):
        resolve_plugin_class("model", "SingleWord")


# ---------------------------------------------------------------------------
# Plugin instantiation tests
# ---------------------------------------------------------------------------


async def test_load_plugin_with_config():
    """load_plugin instantiates class with config kwargs."""
    provider = load_plugin(
        "model",
        "tests.integration.test_m2_3_plugins.MockModelProvider",
        {"model": "custom-v2", "temperature": 0.9},
    )
    assert isinstance(provider, MockModelProvider)
    assert provider.model == "custom-v2"
    assert provider.temperature == 0.9


async def test_load_plugin_no_config():
    """load_plugin works with no config (uses defaults)."""
    store = load_plugin("state", "in_memory")
    assert isinstance(store, InMemoryStateStore)


async def test_load_plugin_bad_config_raises():
    """load_plugin with wrong constructor args produces clear error."""
    with pytest.raises(PluginError) as exc_info:
        load_plugin(
            "state",
            "in_memory",
            {"totally_invalid_kwarg": True},
        )
    assert "Constructor error" in str(exc_info.value)


# ---------------------------------------------------------------------------
# YAML config loading tests
# ---------------------------------------------------------------------------


async def test_load_plugins_from_config_full():
    """load_plugins_from_config loads models, exporters, and state from config dict."""
    config = {
        "plugins": {
            "models": [
                {
                    "type": "tests.integration.test_m2_3_plugins.MockModelProvider",
                    "config": {"model": "test-v1"},
                },
            ],
            "exporters": [
                {
                    "type": "tests.integration.test_m2_3_plugins.MockExporter",
                    "config": {"endpoint": "http://otel:4317"},
                },
            ],
            "state": {
                "type": "tests.integration.test_m2_3_plugins.MockStateStore",
                "config": {"backend": "sqlite"},
            },
        }
    }
    result = load_plugins_from_config(config)

    assert len(result["model_providers"]) == 1
    assert isinstance(result["model_providers"][0], MockModelProvider)
    assert result["model_providers"][0].model == "test-v1"

    assert len(result["exporters"]) == 1
    assert isinstance(result["exporters"][0], MockExporter)
    assert result["exporters"][0].endpoint == "http://otel:4317"

    assert isinstance(result["state_store"], MockStateStore)
    assert result["state_store"].backend == "sqlite"


async def test_load_plugins_multiple_models():
    """Multiple model providers can be configured simultaneously."""
    config = {
        "plugins": {
            "models": [
                {
                    "type": "tests.integration.test_m2_3_plugins.MockModelProvider",
                    "config": {"model": "gpt-4"},
                },
                {
                    "type": "tests.integration.test_m2_3_plugins.MockModelProvider",
                    "config": {"model": "claude-3"},
                },
            ],
        }
    }
    result = load_plugins_from_config(config)
    assert len(result["model_providers"]) == 2
    assert result["model_providers"][0].model == "gpt-4"
    assert result["model_providers"][1].model == "claude-3"


async def test_load_plugins_multiple_exporters():
    """Multiple exporters can be configured simultaneously."""
    config = {
        "plugins": {
            "exporters": [
                {
                    "type": "tests.integration.test_m2_3_plugins.MockExporter",
                    "config": {"endpoint": "http://otel:4317"},
                },
                {
                    "type": "tests.integration.test_m2_3_plugins.MockExporter",
                    "config": {"endpoint": "http://fiddler:8080"},
                },
            ],
        }
    }
    result = load_plugins_from_config(config)
    assert len(result["exporters"]) == 2
    assert result["exporters"][0].endpoint == "http://otel:4317"
    assert result["exporters"][1].endpoint == "http://fiddler:8080"


async def test_load_plugins_empty_config():
    """Empty plugins config returns empty results."""
    result = load_plugins_from_config({})
    assert result["model_providers"] == []
    assert result["exporters"] == []
    assert result["state_store"] is None


async def test_load_plugins_no_state():
    """Missing state config leaves state_store as None."""
    config = {
        "plugins": {
            "models": [
                {"type": "tests.integration.test_m2_3_plugins.MockModelProvider"},
            ],
        }
    }
    result = load_plugins_from_config(config)
    assert result["state_store"] is None
    assert len(result["model_providers"]) == 1


# ---------------------------------------------------------------------------
# Runtime integration tests
# ---------------------------------------------------------------------------


class EchoAgent(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        return self.reply({"echo": message.payload.get("text", "")})


async def test_runtime_from_config_loads_plugins():
    """Runtime.from_config reads plugins section and wires them."""
    yaml_content = """
plugins:
  models:
    - type: tests.integration.test_m2_3_plugins.MockModelProvider
      config:
        model: "config-model"
  state:
    type: tests.integration.test_m2_3_plugins.MockStateStore
    config:
      backend: "test-db"

supervision:
  name: root
  strategy: ONE_FOR_ONE
  children: []
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        runtime = Runtime.from_config(f.name)

    assert isinstance(runtime._model_provider, MockModelProvider)
    assert runtime._model_provider.model == "config-model"
    assert isinstance(runtime._state_store, MockStateStore)
    assert runtime._state_store.backend == "test-db"

    os.unlink(f.name)


async def test_runtime_from_config_plugins_wired_to_agents():
    """Plugins loaded from config are properly injected into agents."""
    yaml_content = """
plugins:
  models:
    - type: tests.integration.test_m2_3_plugins.MockModelProvider
      config:
        model: "injected-model"

supervision:
  name: root
  strategy: ONE_FOR_ONE
  children:
    - agent:
        name: echo
        type: tests.integration.test_m2_3_plugins.EchoAgent
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        runtime = Runtime.from_config(f.name)

    await runtime.start()
    try:
        agent = runtime.get_agent("echo")
        assert agent is not None
        # Verify the model provider was injected
        assert isinstance(agent.llm, MockModelProvider)
        assert agent.llm.model == "injected-model"

        # Agent still works normally
        result = await runtime.ask("echo", {"text": "hello"})
        assert result.payload["echo"] == "hello"
    finally:
        await runtime.stop()

    os.unlink(f.name)


async def test_plugin_load_failure_clear_error():
    """Plugin load failure produces clear error with pip install hint."""
    with pytest.raises(PluginError) as exc_info:
        load_plugin("model", "totally_fake_plugin")

    err = exc_info.value
    assert "totally_fake_plugin" in str(err)
    assert "pip install" in str(err)


async def test_custom_plugin_via_dotted_path():
    """Custom user-written plugin loads via dotted Python path."""
    provider = load_plugin(
        "model",
        "tests.integration.test_m2_3_plugins.MockModelProvider",
    )
    assert isinstance(provider, MockModelProvider)
    response = await provider.chat(model="test", messages=[])
    assert response.content == "mock response"


# ---------------------------------------------------------------------------
# F07-5: InMemoryStateStore copy-on-set
# ---------------------------------------------------------------------------


async def test_in_memory_state_store_set_copies_dict():
    """InMemoryStateStore.set() stores a copy, not the original reference."""
    store = InMemoryStateStore()
    state = {"key": "value"}
    await store.set("agent1", state)

    # Mutate original after storing
    state["key"] = "mutated"

    restored = await store.get("agent1")
    assert restored is not None
    assert restored["key"] == "value"  # stored copy is unchanged


async def test_in_memory_state_store_delete():
    """InMemoryStateStore.delete() removes stored state; get() returns None after."""
    store = InMemoryStateStore()
    await store.set("agent1", {"x": 1})
    assert await store.get("agent1") is not None
    await store.delete("agent1")
    assert await store.get("agent1") is None
    # Deleting a non-existent key is a no-op (no exception)
    await store.delete("agent1")


# ---------------------------------------------------------------------------
# F07-6: ToolRegistry.register() raises on duplicate
# ---------------------------------------------------------------------------


async def test_tool_registry_duplicate_raises():
    """ToolRegistry.register() raises ValueError on duplicate tool name."""

    class FakeTool:
        name = "search"
        schema: dict = {}

        async def execute(self, **kwargs):
            return {}

    registry = ToolRegistry()
    registry.register(FakeTool())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeTool())


async def test_tool_registry_deregister_allows_reregister():
    """Deregistering a tool allows re-registering with the same name."""

    class FakeTool:
        name = "search"
        schema: dict = {}

        async def execute(self, **kwargs):
            return {}

    registry = ToolRegistry()
    registry.register(FakeTool())
    registry.deregister("search")
    registry.register(FakeTool())  # should not raise
    assert registry.get("search") is not None


async def test_tool_registry_list_tools():
    """ToolRegistry.list_tools() returns all registered tools."""

    class FakeToolA:
        name = "tool_a"
        schema: dict = {}

        async def execute(self, **kwargs):
            return {}

    class FakeToolB:
        name = "tool_b"
        schema: dict = {}

        async def execute(self, **kwargs):
            return {}

    registry = ToolRegistry()
    registry.register(FakeToolA())
    registry.register(FakeToolB())
    tools = registry.list_tools()
    assert len(tools) == 2
    assert {t.name for t in tools} == {"tool_a", "tool_b"}


# ---------------------------------------------------------------------------
# F07-7: PluginError in CivitasError hierarchy
# ---------------------------------------------------------------------------


async def test_plugin_error_is_agency_error():
    """PluginError is a subclass of CivitasError."""
    assert issubclass(AgencyPluginError, CivitasError)

    err = AgencyPluginError("model", "fake", "not found")
    assert isinstance(err, CivitasError)


async def test_plugin_error_importable_from_loader():
    """PluginError is still importable from civitas.plugins.loader."""
    assert LoaderPluginError is AgencyPluginError


# ---------------------------------------------------------------------------
# F07-10: missing 'type' field in plugin config raises clear error
# ---------------------------------------------------------------------------


async def test_load_plugins_missing_type_raises():
    """Config entry missing 'type' field raises PluginError with clear message."""
    config = {
        "plugins": {
            "models": [{"config": {"model": "gpt-4"}}],  # no 'type'
        }
    }
    with pytest.raises(PluginError, match="missing a 'type' field"):
        load_plugins_from_config(config)


async def test_load_plugins_missing_exporter_type_raises():
    """Exporter config missing 'type' field raises PluginError."""
    config = {
        "plugins": {
            "exporters": [{"config": {}}],  # no 'type'
        }
    }
    with pytest.raises(PluginError, match="missing a 'type' field"):
        load_plugins_from_config(config)
