import sys

from uuid import uuid4

import httpx
import mcp.types as mcp_types
import pytest

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import (
    Message,
    Task,
    TaskState,
    TextPart,
)
from a2a.utils.message import get_message_text

from hosts.mcp_a2a_gateway.card_generator import (
    generate_agent_card_from_mcp_tools,
    tool_to_agent_skill,
)
from hosts.mcp_a2a_gateway.mcp_client import (
    McpClientConfig,
    McpClientManager,
)
from hosts.mcp_a2a_gateway.server import (
    build_gateway_starlette_app,
)


@pytest.mark.asyncio
async def test_card_generation() -> None:
    """Test converting MCP tools to A2A AgentCard and AgentSkills."""
    mock_tool = mcp_types.Tool(
        name='fetch_user_profile',
        description='Fetch user account details by ID.',
        inputSchema={
            'type': 'object',
            'properties': {'user_id': {'type': 'string'}},
            'required': ['user_id'],
        },
    )

    skill = tool_to_agent_skill(mock_tool)
    assert skill.name == 'fetch_user_profile'
    assert 'mcp-tool' in skill.tags
    assert 'user_id' in skill.tags

    card = generate_agent_card_from_mcp_tools([mock_tool], base_url='http://localhost:9095')
    assert card.name == 'MCP Gateway Agent'
    assert card.url == 'http://localhost:9095'
    assert len(card.skills) == 1
    assert card.skills[0].name == 'fetch_user_profile'


@pytest.mark.asyncio
async def test_mcp_client_stdio_tools() -> None:
    """Test connecting to the sample MCP server over stdio and calling tools."""
    config = McpClientConfig(
        transport='stdio',
        command=sys.executable,
        args=['-m', 'hosts.mcp_a2a_gateway.sample_mcp_server'],
    )
    client_manager = McpClientManager(config=config)

    async with client_manager.session_context():
        tools = await client_manager.list_tools()
        tool_names = [t.name for t in tools]
        assert 'query_database' in tool_names
        assert 'get_system_metrics' in tool_names
        assert 'calculate_financial_roi' in tool_names

        # Call query_database
        result = await client_manager.call_tool(
            'query_database',
            {'sql': 'SELECT name, price FROM products WHERE price > 200'},
        )
        assert not result.isError
        assert len(result.content) > 0
        raw_text = result.content[0].text
        assert 'BigQuery Compute Unit' in raw_text or 'AI Inference Node' in raw_text


@pytest.mark.asyncio
async def test_end_to_end_gateway_flow() -> None:
    """Test full end-to-end flow: Card Resolution -> Task Send -> Artifact Validation."""
    test_host = '127.0.0.1'
    test_port = 9090
    base_url = f'http://{test_host}:{test_port}'

    config = McpClientConfig(
        transport='stdio',
        command=sys.executable,
        args=['-m', 'hosts.mcp_a2a_gateway.sample_mcp_server'],
    )
    mcp_client = McpClientManager(config=config)

    try:
        app, _ = await build_gateway_starlette_app(
            mcp_client=mcp_client,
            host=test_host,
            port=test_port,
            server_name='Test E2E Gateway',
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as http_client:
            # 1. Resolve AgentCard
            resolver = A2ACardResolver(httpx_client=http_client, base_url=base_url)
            card = await resolver.get_agent_card()
            assert card.name == 'Test E2E Gateway'
            assert any(s.name == 'query_database' for s in card.skills)

            # 2. Invoke tool via ClientFactory
            factory = ClientFactory(ClientConfig(httpx_client=http_client))
            a2a_client = factory.create(card)

            msg = Message(
                role='user',
                parts=[
                    TextPart(
                        text='call query_database {"sql": "SELECT * FROM products WHERE price = 120.0"}'
                    )
                ],
                message_id=str(uuid4()),
            )

            events = [event async for event in a2a_client.send_message(msg)]
            assert len(events) > 0

            final_event = events[-1]
            final_item = final_event[0] if isinstance(final_event, tuple) else final_event

            assert isinstance(final_item, Task)
            assert final_item.status.state == TaskState.completed
            assert len(final_item.artifacts) == 1
            assert final_item.artifacts[0].name == 'query_database_result'
            assert 'Cloud Storage Pro' in get_message_text(final_item.status.message)

            # 3. Test financial calculation tool
            msg_calc = Message(
                role='user',
                parts=[
                    TextPart(
                        text='call calculate_financial_roi {"investment": 1000, "annual_gain": 250, "years": 5}'
                    )
                ],
                message_id=str(uuid4()),
            )

            events_calc = [event async for event in a2a_client.send_message(msg_calc)]
            final_calc = (
                events_calc[-1][0] if isinstance(events_calc[-1], tuple) else events_calc[-1]
            )
            assert isinstance(final_calc, Task)
            assert final_calc.status.state == TaskState.completed
            assert 'roi_percentage' in get_message_text(final_calc.status.message)

            # 4. Test unknown query / catalog overview
            msg_overview = Message(
                role='user',
                parts=[TextPart(text='What can you do?')],
                message_id=str(uuid4()),
            )

            events_overview = [event async for event in a2a_client.send_message(msg_overview)]
            final_overview = (
                events_overview[-1][0]
                if isinstance(events_overview[-1], tuple)
                else events_overview[-1]
            )
            assert isinstance(final_overview, Task)
            assert final_overview.status.state == TaskState.completed
            overview_text = get_message_text(final_overview.status.message)
            assert 'query_database' in overview_text
            assert 'get_system_metrics' in overview_text

            # 5. Test invalid tool execution / error handling
            msg_error = Message(
                role='user',
                parts=[TextPart(text='call query_database {"sql": "DROP TABLE products"}')],
                message_id=str(uuid4()),
            )

            events_error = [event async for event in a2a_client.send_message(msg_error)]
            final_error = (
                events_error[-1][0] if isinstance(events_error[-1], tuple) else events_error[-1]
            )
            assert isinstance(final_error, Task)
            assert final_error.status.state == TaskState.failed
            assert 'Only SELECT queries are permitted' in get_message_text(
                final_error.status.message
            )

    finally:
        await mcp_client.disconnect()
