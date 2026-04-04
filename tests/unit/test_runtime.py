"""Unit tests for Runtime — config parsing, tree rendering, agent lookup, lifecycle guards."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agency import AgentProcess, Runtime, Supervisor
from agency.config import SecretStr, Settings
from agency.errors import ConfigurationError as AgencyConfigError
from agency.messages import Message
from agency.process import ProcessStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class NullAgent(AgentProcess):
    async def handle(self, message: Message) -> None:
        return None


# ---------------------------------------------------------------------------
# Settings — frozen at instantiation, validated, SecretStr
# ---------------------------------------------------------------------------

class TestSettings:
    def test_default_serializer_is_msgpack(self):
        s = Settings(env={})
        assert s.serializer == "msgpack"

    def test_json_serializer_accepted(self):
        s = Settings(env={"AGENCY_SERIALIZER": "json"})
        assert s.serializer == "json"

    def test_invalid_serializer_raises(self):
        with pytest.raises(AgencyConfigError, match="AGENCY_SERIALIZER"):
            Settings(env={"AGENCY_SERIALIZER": "grpc"})

    def test_frozen_at_instantiation(self):
        # Values are attributes, not dynamic property lookups
        s = Settings(env={"AGENCY_SERIALIZER": "json"})
        assert isinstance(s.serializer, str)

    def test_secret_str_masked_in_repr(self):
        s = Settings(env={"ANTHROPIC_API_KEY": "sk-secret"})
        r = repr(s.anthropic_api_key)
        assert "sk-secret" not in r
        assert "**" in r

    def test_secret_str_masked_in_str(self):
        s = Settings(env={"OPENAI_API_KEY": "openai-abc"})
        assert "openai-abc" not in str(s.openai_api_key)

    def test_secret_str_get_returns_value(self):
        s = Settings(env={"ANTHROPIC_API_KEY": "sk-real"})
        assert s.anthropic_api_key.get() == "sk-real"

    def test_secret_str_none_is_falsy(self):
        s = Settings(env={})
        assert not s.anthropic_api_key

    def test_secret_str_with_value_is_truthy(self):
        s = Settings(env={"ANTHROPIC_API_KEY": "x"})
        assert s.anthropic_api_key

    def test_otel_endpoint_none_when_missing(self):
        s = Settings(env={})
        assert s.otel_endpoint is None

    def test_nats_url_default(self):
        s = Settings(env={})
        assert s.nats_url == "nats://localhost:4222"


# ---------------------------------------------------------------------------
# Runtime.print_tree
# ---------------------------------------------------------------------------

class TestPrintTree:
    def test_no_supervisor_returns_placeholder(self):
        rt = Runtime()
        assert rt.print_tree() == "(no supervision tree)"

    def test_flat_tree(self):
        rt = Runtime(supervisor=Supervisor("root", children=[NullAgent("a"), NullAgent("b")]))
        tree = rt.print_tree()
        assert "root" in tree
        assert "a" in tree
        assert "b" in tree

    def test_nested_tree_shows_child_supervisor(self):
        child_sup = Supervisor("workers", children=[NullAgent("w1")])
        root = Supervisor("root", children=[NullAgent("gatekeeper"), child_sup])
        rt = Runtime(supervisor=root)
        tree = rt.print_tree()
        assert "workers" in tree
        assert "w1" in tree
        assert "gatekeeper" in tree


# ---------------------------------------------------------------------------
# Runtime.get_agent
# ---------------------------------------------------------------------------

class TestGetAgent:
    def test_returns_none_before_start(self):
        agent = NullAgent("a")
        rt = Runtime(supervisor=Supervisor("root", children=[agent]))
        assert rt.get_agent("a") is None

    def test_returns_none_for_no_supervisor(self):
        rt = Runtime()
        assert rt.get_agent("anything") is None

    @pytest.mark.asyncio
    async def test_returns_agent_after_start(self):
        agent = NullAgent("a")
        rt = Runtime(supervisor=Supervisor("root", children=[agent]))
        await rt.start()
        try:
            assert rt.get_agent("a") is agent
        finally:
            await rt.stop()

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_name(self):
        rt = Runtime(supervisor=Supervisor("root", children=[NullAgent("a")]))
        await rt.start()
        try:
            assert rt.get_agent("missing") is None
        finally:
            await rt.stop()

    @pytest.mark.asyncio
    async def test_returns_none_after_stop(self):
        rt = Runtime(supervisor=Supervisor("root", children=[NullAgent("a")]))
        await rt.start()
        await rt.stop()
        assert rt.get_agent("a") is None


# ---------------------------------------------------------------------------
# Runtime.start / stop lifecycle guards
# ---------------------------------------------------------------------------

class TestLifecycleGuards:
    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        rt = Runtime(supervisor=Supervisor("root", children=[NullAgent("a")]))
        await rt.start()
        try:
            # Second start should be a no-op, not raise
            await rt.start()
            assert rt._started is True
        finally:
            await rt.stop()

    @pytest.mark.asyncio
    async def test_stop_on_unstarted_runtime_is_safe(self):
        rt = Runtime()
        # Should not raise
        await rt.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_started_flag(self):
        rt = Runtime(supervisor=Supervisor("root", children=[NullAgent("a")]))
        await rt.start()
        await rt.stop()
        assert rt._started is False


# ---------------------------------------------------------------------------
# Runtime.from_config — YAML parsing
# ---------------------------------------------------------------------------

class TestFromConfig:
    def test_missing_supervision_key_raises(self, tmp_path: Path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(textwrap.dedent("""\
            transport:
              type: in_process
        """))
        with pytest.raises(AgencyConfigError, match="supervision"):
            Runtime.from_config(bad_yaml)

    def test_typo_key_raises(self, tmp_path: Path):
        bad_yaml = tmp_path / "typo.yaml"
        bad_yaml.write_text(textwrap.dedent("""\
            supervison:
              name: root
        """))
        with pytest.raises(AgencyConfigError, match="supervision"):
            Runtime.from_config(bad_yaml)

    def test_bad_agent_type_raises_configuration_error(self, tmp_path: Path):
        bad_yaml = tmp_path / "bad_type.yaml"
        bad_yaml.write_text(textwrap.dedent("""\
            supervision:
              name: root
              children:
                - type: "nonexistent.module.FakeAgent"
                  name: "fake"
        """))
        with pytest.raises(AgencyConfigError, match="Cannot load agent type"):
            Runtime.from_config(bad_yaml)

    def test_unresolvable_short_name_raises(self, tmp_path: Path):
        bad_yaml = tmp_path / "short.yaml"
        bad_yaml.write_text(textwrap.dedent("""\
            supervision:
              name: root
              children:
                - type: "NoModule"
                  name: "x"
        """))
        with pytest.raises((AgencyConfigError, ValueError)):
            Runtime.from_config(bad_yaml)

    def test_valid_minimal_config(self, tmp_path: Path):
        """A supervision key with no children produces a runtime without error."""
        yaml_file = tmp_path / "minimal.yaml"
        yaml_file.write_text(textwrap.dedent("""\
            supervision:
              name: root
        """))
        rt = Runtime.from_config(yaml_file)
        assert rt._root_supervisor is not None
        assert rt._root_supervisor.name == "root"

    def test_agent_classes_dict_resolution(self, tmp_path: Path):
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(textwrap.dedent("""\
            supervision:
              name: root
              children:
                - type: "NullAgent"
                  name: "worker"
        """))
        rt = Runtime.from_config(yaml_file, agent_classes={"NullAgent": NullAgent})
        agents = rt._root_supervisor.all_agents()
        assert len(agents) == 1
        assert agents[0].name == "worker"
        assert isinstance(agents[0], NullAgent)
