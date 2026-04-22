"""MCPClient — manages a persistent connection to one MCP server."""

from __future__ import annotations

import contextlib
from typing import Any

from civitas.mcp.types import MCPServerConfig, MCPToolError, MCPToolSchema

try:
    from mcp import ClientSession, StdioServerParameters, stdio_client
    from mcp.client.sse import sse_client

    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


class MCPClient:
    """Manages a single persistent MCP connection (one session per agent per server).

    Lifecycle:
        client = MCPClient(config)
        await client.connect()          # open session, initialize
        schemas = await client.list_tools()
        result  = await client.call_tool("tool_name", {"arg": "value"})
        await client.disconnect()       # close session and subprocess/connection

    One MCPClient per server per agent. Shared pooling across agents is Fabrica's job.
    """

    def __init__(self, config: MCPServerConfig) -> None:
        if not _HAS_MCP:
            raise ImportError(
                "civitas[mcp] is required for MCP integration. "
                "Install it with: pip install 'civitas[mcp]'"
            )
        self.config = config
        self._session: Any = None  # ClientSession when connected
        self._exit_stack = contextlib.AsyncExitStack()

    async def connect(self) -> None:
        """Open transport, initialize ClientSession. Must be called before list_tools/call_tool."""
        if self._session is not None:
            return  # already connected

        if self.config.transport == "stdio":
            assert self.config.command is not None  # validated by MCPServerConfig.__post_init__
            params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args or [],
                env=self.config.env,
            )
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        else:
            assert self.config.url is not None  # validated by MCPServerConfig.__post_init__
            read, write = await self._exit_stack.enter_async_context(sse_client(self.config.url))

        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session

    async def disconnect(self) -> None:
        """Close the session and underlying transport."""
        await self._exit_stack.aclose()
        self._session = None

    async def list_tools(self) -> list[MCPToolSchema]:
        """Return all tools exposed by this MCP server."""
        self._require_connected()
        result = await self._session.list_tools()
        return [
            MCPToolSchema(
                name=tool.name,
                description=tool.description or "",
                input_schema=dict(tool.inputSchema) if tool.inputSchema else {},
            )
            for tool in result.tools
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool by name with the given arguments.

        Returns extracted text if all content items are text, otherwise the raw content list.
        Raises MCPToolError if the server returns isError=True.
        """
        self._require_connected()
        result = await self._session.call_tool(tool_name, arguments)
        if result.isError:
            detail = " ".join(item.text for item in result.content if hasattr(item, "text")) or str(
                result.content
            )
            raise MCPToolError(tool_name, detail)

        texts = [item.text for item in result.content if hasattr(item, "text")]
        if texts and len(texts) == len(result.content):
            return "\n".join(texts)
        return result.content

    def _require_connected(self) -> None:
        if self._session is None:
            raise RuntimeError(
                f"MCPClient '{self.config.name}' is not connected. "
                "Call await client.connect() first."
            )
