"""MCPTool — ToolProvider backed by an MCPClient."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from civitas.mcp.types import MCPToolSchema

if TYPE_CHECKING:
    from civitas.mcp.client import MCPClient
    from civitas.observability.tracer import Tracer


class MCPTool:
    """A ToolProvider wrapping a single MCP tool.

    Name follows the mcp://server_name/tool_name convention so agents can
    look up tools by direct address:

        tool = self.tools.get("mcp://github/create_issue")
        result = await tool.execute(title="Bug", repo="owner/repo")
    """

    def __init__(
        self,
        client: MCPClient,
        schema: MCPToolSchema,
        tracer: Tracer | None = None,
    ) -> None:
        self._client = client
        self._schema = schema
        self._tracer = tracer

    @property
    def name(self) -> str:
        """mcp://server_name/tool_name — used as the ToolRegistry key."""
        return f"mcp://{self._client.config.name}/{self._schema.name}"

    @property
    def schema(self) -> dict[str, Any]:
        """JSON Schema for this tool's input parameters."""
        return self._schema.input_schema

    async def execute(self, **kwargs: Any) -> Any:
        """Call the MCP tool. Emits a civitas.mcp.call OTEL span."""
        span = None
        if self._tracer is not None:
            span = self._tracer.start_span(
                "civitas.mcp.call",
                attributes={
                    "civitas.mcp.server": self._client.config.name,
                    "civitas.mcp.tool": self._schema.name,
                    "civitas.mcp.transport": self._client.config.transport,
                },
            )
        try:
            result = await self._client.call_tool(self._schema.name, kwargs)
            if span is not None:
                span.set_attribute("civitas.handle.result", "success")
            return result
        except Exception as exc:
            if span is not None:
                span.set_error(exc)
            raise
        finally:
            if span is not None:
                span.end()
