import contextlib
import logging

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import mcp.types as mcp_types

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client


logger = logging.getLogger('mcp_a2a_gateway.mcp_client')


@dataclass
class McpClientConfig:
    """Configuration for connecting to an MCP server."""

    transport: str = 'stdio'  # 'stdio' or 'sse'
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    sse_url: str | None = None


class McpClientManager:
    """Manages the lifecycle of an MCP client connection."""

    def __init__(self, config: McpClientConfig) -> None:
        self.config = config
        self.session: ClientSession | None = None
        self._exit_stack = contextlib.AsyncExitStack()

    async def connect(self) -> ClientSession:
        """Establish connection to the MCP server and initialize session."""
        if self.config.transport == 'stdio':
            if not self.config.command:
                raise ValueError('Command must be provided for stdio transport.')
            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args or [],
                env=self.config.env,
            )
            read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
        elif self.config.transport == 'sse':
            if not self.config.sse_url:
                raise ValueError('sse_url must be provided for SSE transport.')
            read, write = await self._exit_stack.enter_async_context(
                sse_client(self.config.sse_url)
            )
        else:
            raise ValueError(f'Unsupported transport: {self.config.transport}')

        self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        logger.info('Initialized MCP ClientSession successfully.')
        return self.session

    async def list_tools(self) -> list[mcp_types.Tool]:
        """Fetch all available tools from the connected MCP server."""
        if not self.session:
            raise RuntimeError('MCP session is not connected.')
        result = await self.session.list_tools()
        return list(result.tools)

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> mcp_types.CallToolResult:
        """Invoke a tool on the connected MCP server."""
        if not self.session:
            raise RuntimeError('MCP session is not connected.')
        return await self.session.call_tool(name=name, arguments=arguments or {})

    async def disconnect(self) -> None:
        """Cleanly terminate the MCP session and underlying transports."""
        await self._exit_stack.aclose()
        self.session = None
        logger.info('Disconnected MCP ClientSession.')

    @contextlib.asynccontextmanager
    async def session_context(self) -> AsyncIterator[ClientSession]:
        """Context manager for managing MCP client connection lifecycle."""
        try:
            session = await self.connect()
            yield session
        finally:
            await self.disconnect()
