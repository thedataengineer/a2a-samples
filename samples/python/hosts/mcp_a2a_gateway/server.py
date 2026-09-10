import logging

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from starlette.applications import Starlette

from hosts.mcp_a2a_gateway.card_generator import (
    generate_agent_card_from_mcp_tools,
)
from hosts.mcp_a2a_gateway.executor import McpGatewayExecutor
from hosts.mcp_a2a_gateway.mcp_client import McpClientManager


logger = logging.getLogger('mcp_a2a_gateway.server')


async def build_gateway_starlette_app(
    mcp_client: McpClientManager,
    host: str = '127.0.0.1',
    port: int = 9090,
    server_name: str = 'MCP-to-A2A Dynamic Gateway',
) -> tuple[Starlette, AgentCard]:
    """Connect to MCP, introspect tools, and build Starlette A2A application."""
    if not mcp_client.session:
        await mcp_client.connect()

    # Discover MCP tools
    tools = await mcp_client.list_tools()
    logger.info('Discovered %d MCP tools for A2A Gateway.', len(tools))

    # Generate A2A AgentCard dynamically
    base_url = f'http://{host}:{port}'
    agent_card = generate_agent_card_from_mcp_tools(
        tools=tools,
        server_name=server_name,
        base_url=base_url,
    )

    # Build Executor and RequestHandler
    executor = McpGatewayExecutor(mcp_client=mcp_client)
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    # Build Starlette ASGI app
    gateway_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    ).build()

    return gateway_app, agent_card
