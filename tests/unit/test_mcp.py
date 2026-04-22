"""Unit tests for MCP integration — types, MCPTool, connect_mcp(), topology YAML."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from civitas.mcp.tool import MCPTool
from civitas.mcp.types import MCPServerConfig, MCPToolError, MCPToolSchema
from civitas.plugins.tools import ToolRegistry

# ---------------------------------------------------------------------------
# MCPServerConfig validation
# ---------------------------------------------------------------------------


class TestMCPServerConfig:
    def test_stdio_requires_command(self):
        with pytest.raises(ValueError, match="requires 'command'"):
            MCPServerConfig(name="x", transport="stdio")

    def test_sse_requires_url(self):
        with pytest.raises(ValueError, match="requires 'url'"):
            MCPServerConfig(name="x", transport="sse")

    def test_unknown_transport_raises(self):
        with pytest.raises(ValueError, match="unknown transport"):
            MCPServerConfig(name="x", transport="grpc", command="cmd")  # type: ignore[arg-type]

    def test_stdio_valid(self):
        cfg = MCPServerConfig(name="github", transport="stdio", command="npx")
        assert cfg.name == "github"
        assert cfg.transport == "stdio"
        assert cfg.command == "npx"
        assert cfg.args == []
        assert cfg.env is None

    def test_sse_valid(self):
        cfg = MCPServerConfig(name="remote", transport="sse", url="http://localhost:8080")
        assert cfg.url == "http://localhost:8080"

    def test_stdio_with_args_and_env(self):
        cfg = MCPServerConfig(
            name="fs",
            transport="stdio",
            command="npx",
            args=["-y", "@mcp/fs", "/tmp"],
            env={"TOKEN": "abc"},
        )
        assert cfg.args == ["-y", "@mcp/fs", "/tmp"]
        assert cfg.env == {"TOKEN": "abc"}


# ---------------------------------------------------------------------------
# MCPToolError
# ---------------------------------------------------------------------------


class TestMCPToolError:
    def test_str_includes_tool_name_and_detail(self):
        err = MCPToolError("create_issue", "not found")
        assert "create_issue" in str(err)
        assert "not found" in str(err)

    def test_attributes(self):
        err = MCPToolError("search", "timeout")
        assert err.tool_name == "search"
        assert err.detail == "timeout"


# ---------------------------------------------------------------------------
# MCPToolSchema
# ---------------------------------------------------------------------------


class TestMCPToolSchema:
    def test_fields(self):
        schema = MCPToolSchema(
            name="create_issue",
            description="Creates a GitHub issue",
            input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        )
        assert schema.name == "create_issue"
        assert schema.description == "Creates a GitHub issue"
        assert "title" in schema.input_schema["properties"]


# ---------------------------------------------------------------------------
# MCPTool
# ---------------------------------------------------------------------------


def _make_tool(
    server_name: str = "github",
    tool_name: str = "create_issue",
    tracer: Any = None,
) -> tuple[MCPTool, MagicMock]:
    """Return (MCPTool, mock_client) pair."""
    schema = MCPToolSchema(
        name=tool_name,
        description="Test tool",
        input_schema={"type": "object"},
    )
    client = MagicMock()
    client.config.name = server_name
    client.config.transport = "stdio"
    client.call_tool = AsyncMock(return_value="ok")
    return MCPTool(client, schema, tracer=tracer), client


class TestMCPTool:
    def test_name_follows_mcp_uri(self):
        tool, _ = _make_tool("github", "create_issue")
        assert tool.name == "mcp://github/create_issue"

    def test_schema_returns_input_schema(self):
        schema = MCPToolSchema(
            name="t",
            description="",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        )
        client = MagicMock()
        client.config.name = "srv"
        t = MCPTool(client, schema)
        assert t.schema == {"type": "object", "properties": {"x": {"type": "integer"}}}

    @pytest.mark.asyncio
    async def test_execute_delegates_to_client(self):
        tool, client = _make_tool()
        result = await tool.execute(title="Bug", body="details")
        client.call_tool.assert_called_once_with(
            "create_issue", {"title": "Bug", "body": "details"}
        )
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_execute_propagates_mcp_tool_error(self):
        tool, client = _make_tool()
        client.call_tool = AsyncMock(side_effect=MCPToolError("create_issue", "server error"))
        with pytest.raises(MCPToolError, match="server error"):
            await tool.execute(title="Bug")

    @pytest.mark.asyncio
    async def test_execute_emits_span_on_success(self):
        tracer = MagicMock()
        span = MagicMock()
        tracer.start_span.return_value = span
        tool, _ = _make_tool(tracer=tracer)
        await tool.execute(x=1)
        tracer.start_span.assert_called_once()
        span.set_attribute.assert_called_once_with("civitas.handle.result", "success")
        span.end.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_records_span_error_on_failure(self):
        tracer = MagicMock()
        span = MagicMock()
        tracer.start_span.return_value = span
        tool, client = _make_tool(tracer=tracer)
        client.call_tool = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            await tool.execute()
        span.set_error.assert_called_once()
        span.end.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_works_without_tracer(self):
        tool, _ = _make_tool(tracer=None)
        result = await tool.execute(x=1)
        assert result == "ok"


# ---------------------------------------------------------------------------
# ToolRegistry.deregister_prefix
# ---------------------------------------------------------------------------


class TestToolRegistryDeregisterPrefix:
    def test_removes_all_matching_tools(self):
        registry = ToolRegistry()
        for name in ("mcp://github/create_issue", "mcp://github/list_issues", "mcp://fs/read"):
            t = MagicMock()
            t.name = name
            registry.register(t)

        registry.deregister_prefix("mcp://github/")
        assert registry.get("mcp://github/create_issue") is None
        assert registry.get("mcp://github/list_issues") is None
        assert registry.get("mcp://fs/read") is not None

    def test_no_op_for_unknown_prefix(self):
        registry = ToolRegistry()
        registry.deregister_prefix("mcp://nonexistent/")  # should not raise


# ---------------------------------------------------------------------------
# AgentProcess.connect_mcp()
# ---------------------------------------------------------------------------


class TestAgentConnectMcp:
    @pytest.mark.asyncio
    async def test_connect_mcp_registers_tools(self):
        from civitas.messages import Message
        from civitas.process import AgentProcess

        class NullAgent(AgentProcess):
            async def handle(self, message: Message) -> None:
                return None

        agent = NullAgent("test-agent")
        registry = ToolRegistry()
        agent.tools = registry

        cfg = MCPServerConfig(name="github", transport="stdio", command="npx")

        mock_client_instance = MagicMock()
        mock_client_instance.config.name = "github"
        mock_client_instance.connect = AsyncMock()
        mock_client_instance.list_tools = AsyncMock(
            return_value=[
                MCPToolSchema(name="create_issue", description="Create", input_schema={}),
                MCPToolSchema(name="list_issues", description="List", input_schema={}),
            ]
        )

        with patch("civitas.mcp.client.MCPClient", return_value=mock_client_instance):
            await agent.connect_mcp(cfg)

        assert registry.get("mcp://github/create_issue") is not None
        assert registry.get("mcp://github/list_issues") is not None
        assert "github" in agent._mcp_clients

    @pytest.mark.asyncio
    async def test_connect_mcp_is_idempotent(self):
        from civitas.messages import Message
        from civitas.process import AgentProcess

        class NullAgent(AgentProcess):
            async def handle(self, message: Message) -> None:
                return None

        agent = NullAgent("test-agent")
        registry = ToolRegistry()
        agent.tools = registry

        cfg = MCPServerConfig(name="github", transport="stdio", command="npx")

        def _make_client() -> MagicMock:
            m = MagicMock()
            m.config.name = "github"
            m.connect = AsyncMock()
            m.disconnect = AsyncMock()
            m.list_tools = AsyncMock(
                return_value=[MCPToolSchema(name="create_issue", description="", input_schema={})]
            )
            return m

        client1 = _make_client()
        client2 = _make_client()

        with patch("civitas.mcp.client.MCPClient", side_effect=[client1, client2]):
            await agent.connect_mcp(cfg)
            await agent.connect_mcp(cfg)  # reconnect

        # Old client must have been disconnected
        client1.disconnect.assert_called_once()
        # Only one tool should be registered (not duplicated)
        assert len(registry.names()) == 1

    @pytest.mark.asyncio
    async def test_connect_mcp_without_tool_registry(self):
        """connect_mcp() should not raise when self.tools is None."""
        from civitas.messages import Message
        from civitas.process import AgentProcess

        class NullAgent(AgentProcess):
            async def handle(self, message: Message) -> None:
                return None

        agent = NullAgent("no-tools-agent")
        # agent.tools is None by default
        cfg = MCPServerConfig(name="srv", transport="stdio", command="cmd")

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[])

        with patch("civitas.mcp.client.MCPClient", return_value=mock_client):
            await agent.connect_mcp(cfg)  # should not raise


# ---------------------------------------------------------------------------
# Runtime.from_config — mcp.servers parsed into _mcp_configs
# ---------------------------------------------------------------------------


class TestRuntimeMcpConfig:
    def test_mcp_servers_parsed_from_yaml(self, tmp_path: Path):
        topology = textwrap.dedent("""\
            supervision:
              name: root
              strategy: ONE_FOR_ONE
              children: []
            mcp:
              servers:
                - name: github
                  transport: stdio
                  command: npx
                  args: ["-y", "@mcp/server-github"]
                  env:
                    GITHUB_TOKEN: "tok"
                - name: remote
                  transport: sse
                  url: "http://localhost:8080/sse"
        """)
        cfg_file = tmp_path / "topology.yaml"
        cfg_file.write_text(topology)

        from civitas import Runtime

        runtime = Runtime.from_config(cfg_file)
        assert len(runtime._mcp_configs) == 2

        gh = runtime._mcp_configs[0]
        assert gh.name == "github"
        assert gh.transport == "stdio"
        assert gh.command == "npx"
        assert gh.args == ["-y", "@mcp/server-github"]
        assert gh.env == {"GITHUB_TOKEN": "tok"}

        remote = runtime._mcp_configs[1]
        assert remote.name == "remote"
        assert remote.transport == "sse"
        assert remote.url == "http://localhost:8080/sse"

    def test_no_mcp_section_leaves_empty_list(self, tmp_path: Path):
        topology = textwrap.dedent("""\
            supervision:
              name: root
              strategy: ONE_FOR_ONE
              children: []
        """)
        cfg_file = tmp_path / "topology.yaml"
        cfg_file.write_text(topology)

        from civitas import Runtime

        runtime = Runtime.from_config(cfg_file)
        assert runtime._mcp_configs == []
