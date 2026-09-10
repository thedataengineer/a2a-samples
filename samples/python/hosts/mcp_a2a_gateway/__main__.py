import asyncio
import logging
import shlex
import sys

import click
import uvicorn

from hosts.mcp_a2a_gateway.mcp_client import (
    McpClientConfig,
    McpClientManager,
)
from hosts.mcp_a2a_gateway.server import (
    build_gateway_starlette_app,
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('mcp_a2a_gateway')


@click.command()
@click.option(
    '--stdio-command',
    default=None,
    help='Command to spawn an MCP server over stdio. Defaults to built-in sample MCP server.',
)
@click.option(
    '--sse-url',
    default=None,
    help='HTTP/SSE URL of a remote MCP server.',
)
@click.option(
    '--host',
    default='127.0.0.1',
    help='Host IP to bind the A2A JSON-RPC server.',
)
@click.option(
    '--port',
    default=9090,
    type=int,
    help='Port to bind the A2A JSON-RPC server.',
)
@click.option(
    '--name',
    default='Enterprise MCP-to-A2A Gateway',
    help='Name advertised in the generated A2A AgentCard.',
)
def main(
    stdio_command: str | None,
    sse_url: str | None,
    host: str,
    port: int,
    name: str,
) -> None:
    """Launch the MCP-to-A2A Dynamic Protocol Gateway."""
    if sse_url:
        config = McpClientConfig(transport='sse', sse_url=sse_url)
    elif stdio_command:
        parts = shlex.split(stdio_command)
        config = McpClientConfig(
            transport='stdio',
            command=parts[0],
            args=parts[1:] if len(parts) > 1 else [],
        )
    else:
        # Default: Use built-in FastMCP sample server
        logger.info('No external MCP server specified. Launching built-in reference MCP server.')
        config = McpClientConfig(
            transport='stdio',
            command=sys.executable,
            args=['-m', 'hosts.mcp_a2a_gateway.sample_mcp_server'],
        )

    mcp_client = McpClientManager(config=config)

    async def run_server() -> None:
        try:
            app, agent_card = await build_gateway_starlette_app(
                mcp_client=mcp_client,
                host=host,
                port=port,
                server_name=name,
            )

            logger.info('=============================================')
            logger.info('  A2A AgentCard dynamically generated:')
            logger.info('  Name: %s', agent_card.name)
            logger.info('  URL:  %s', agent_card.url)
            logger.info('  Skills: %s', [s.name for s in agent_card.skills])
            logger.info('=============================================')

            server_config = uvicorn.Config(
                app=app,
                host=host,
                port=port,
                log_level='info',
            )
            server = uvicorn.Server(server_config)
            await server.serve()
        finally:
            await mcp_client.disconnect()

    asyncio.run(run_server())


if __name__ == '__main__':
    main()
