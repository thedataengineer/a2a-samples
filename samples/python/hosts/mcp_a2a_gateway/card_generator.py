from typing import Any

import mcp.types as mcp_types

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    TransportProtocol,
)


def tool_to_agent_skill(tool: mcp_types.Tool) -> AgentSkill:
    """Convert an MCP Tool definition to an A2A AgentSkill."""
    examples: list[str] = []
    tags: list[str] = ['mcp-tool', tool.name]

    # Extract parameter descriptions if available in inputSchema
    schema = tool.inputSchema if isinstance(tool.inputSchema, dict) else {}
    props: dict[str, Any] = schema.get('properties', {})
    if props:
        tags.extend(props.keys())

    description = tool.description or f'MCP Tool: {tool.name}'
    if props:
        param_summary = ', '.join(f'{k} ({v.get("type", "any")})' for k, v in props.items())
        description = f'{description}\nParameters: {param_summary}'

    return AgentSkill(
        id=f'mcp-tool-{tool.name}',
        name=tool.name,
        description=description,
        tags=tags,
        examples=examples,
    )


def generate_agent_card_from_mcp_tools(
    tools: list[mcp_types.Tool],
    server_name: str = 'MCP Gateway Agent',
    description: str = 'Dynamic A2A Gateway exposing tools from an MCP server.',
    base_url: str = 'http://127.0.0.1:9090',
    version: str = '1.0.0',
) -> AgentCard:
    """Generate an A2A AgentCard dynamically from a list of MCP tools."""
    skills = [tool_to_agent_skill(tool) for tool in tools]

    return AgentCard(
        name=server_name,
        description=description,
        version=version,
        url=base_url,
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(
            streaming=True,
        ),
        skills=skills,
        additional_interfaces=[
            AgentInterface(
                transport=TransportProtocol.jsonrpc,
                url=base_url,
            )
        ],
    )
