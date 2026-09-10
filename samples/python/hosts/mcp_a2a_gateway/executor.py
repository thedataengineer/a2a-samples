"""Executor module for dynamically routing A2A task requests to MCP tools."""

import json
import logging
import re

from typing import Any

import mcp.types as mcp_types

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    DataPart,
    Part,
    TaskState,
    TextPart,
)
from a2a.utils.message import get_message_text, new_agent_text_message
from a2a.utils.task import new_task

from hosts.mcp_a2a_gateway.mcp_client import McpClientManager


logger = logging.getLogger('mcp_a2a_gateway.executor')


def _parse_json_payload(
    stripped: str, available_tools: dict[str, mcp_types.Tool]
) -> tuple[str | None, dict[str, Any]]:
    """Parse direct JSON dictionary formatted tool requests."""
    if not (stripped.startswith('{') and stripped.endswith('}')):
        return None, {}
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            if 'tool' in data:
                return data.get('tool'), data.get('arguments', {})
            if 'name' in data and data['name'] in available_tools:
                return data['name'], data.get('arguments', data.get('args', {}))
    except json.JSONDecodeError:
        pass
    return None, {}


def _parse_cli_syntax(stripped: str) -> tuple[str | None, dict[str, Any]]:
    """Parse CLI syntax formatted requests: call <tool_name> <json_args>."""
    call_match = re.match(r'^call\s+([a-zA-Z0-9_\-]+)(?:\s+(.*))?$', stripped, re.IGNORECASE)
    if not call_match:
        return None, {}
    tool_name = call_match.group(1)
    raw_args = call_match.group(2)
    args_dict: dict[str, Any] = {}
    if raw_args:
        try:
            args_dict = json.loads(raw_args)
        except json.JSONDecodeError:
            args_dict = {'query': raw_args}
    return tool_name, args_dict


def _parse_function_call(
    stripped: str, available_tools: dict[str, mcp_types.Tool]
) -> tuple[str | None, dict[str, Any]]:
    """Parse function-style formatted requests: tool_name({...})."""
    fn_match = re.match(r'^([a-zA-Z0-9_\-]+)\s*\((.*)\)$', stripped, re.DOTALL)
    if not (fn_match and fn_match.group(1) in available_tools):
        return None, {}
    tool_name = fn_match.group(1)
    raw_args = fn_match.group(2).strip()
    if raw_args.startswith('{') and raw_args.endswith('}'):
        try:
            return tool_name, json.loads(raw_args)
        except json.JSONDecodeError:
            pass
    elif not raw_args:
        return tool_name, {}
    return None, {}


def _extract_artifact_parts(call_result: mcp_types.CallToolResult) -> tuple[list[Part], list[str]]:
    """Extract A2A Parts and readable text strings from MCP CallToolResult."""
    artifact_parts: list[Part] = []
    output_texts: list[str] = []

    for content_item in call_result.content:
        if isinstance(content_item, mcp_types.TextContent):
            output_texts.append(content_item.text)
            artifact_parts.append(Part(root=TextPart(text=content_item.text)))
        elif isinstance(content_item, mcp_types.ImageContent):
            output_texts.append(f'[Image: {content_item.mimeType}]')
            artifact_parts.append(
                Part(
                    root=DataPart(
                        data={
                            'mime_type': content_item.mimeType,
                            'data': content_item.data,
                        }
                    )
                )
            )
        elif isinstance(content_item, mcp_types.EmbeddedResource):
            res = content_item.resource
            output_texts.append(f'[Resource: {res.uri}]')
            artifact_parts.append(
                Part(
                    root=DataPart(
                        data={
                            'uri': str(res.uri),
                            'mime_type': getattr(res, 'mimeType', 'text/plain'),
                        }
                    )
                )
            )

    if call_result.structuredContent:
        artifact_parts.append(Part(root=DataPart(data=call_result.structuredContent)))

    return artifact_parts, output_texts


class McpGatewayExecutor(AgentExecutor):
    """A2A AgentExecutor that dynamically routes requests to underlying MCP tools."""

    def __init__(self, mcp_client: McpClientManager) -> None:
        """Initialize with an active McpClientManager."""
        self.mcp_client = mcp_client

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Process incoming A2A message and execute corresponding MCP tool."""
        task = context.current_task or new_task(context.message)
        await event_queue.enqueue_event(task)

        task_updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )

        user_query = get_message_text(context.message) or ''
        logger.info('Received A2A task request: %s', user_query)

        # 1. Inspect available MCP tools
        try:
            available_tools = await self.mcp_client.list_tools()
            tool_map = {t.name: t for t in available_tools}
        except Exception:
            logger.exception('Failed to list tools from MCP server')
            await task_updater.update_status(
                state=TaskState.failed,
                message=new_agent_text_message('Error communicating with MCP server.'),
            )
            return

        # 2. Parse tool invocation from query
        tool_name, tool_args = self._parse_tool_invocation(user_query, tool_map)

        if not tool_name or tool_name not in tool_map:
            tool_summary_lines = [
                f'- **{name}**: {tool.description or "No description"}'
                for name, tool in tool_map.items()
            ]
            summary_text = (
                f"No specific tool matched query: '{user_query}'.\n\n"
                f'Available MCP Tools in this Gateway:\n'
                + '\n'.join(tool_summary_lines)
                + '\n\nTo invoke a tool, send: `call <tool_name> {"arg": "value"}` or `{"tool": "<tool_name>", "arguments": {...}}`'
            )
            await task_updater.update_status(
                state=TaskState.completed,
                message=new_agent_text_message(summary_text),
            )
            return

        # 3. Update status to working
        await task_updater.update_status(
            state=TaskState.working,
            message=new_agent_text_message(
                f"Executing MCP tool '{tool_name}' with arguments: {json.dumps(tool_args)}"
            ),
        )

        # 4. Invoke MCP tool
        try:
            call_result: mcp_types.CallToolResult = await self.mcp_client.call_tool(
                name=tool_name, arguments=tool_args
            )

            artifact_parts, output_texts = _extract_artifact_parts(call_result)

            if artifact_parts:
                await task_updater.add_artifact(
                    parts=artifact_parts,
                    name=f'{tool_name}_result',
                    metadata={
                        'tool_name': tool_name,
                        'is_error': call_result.isError,
                    },
                )

            final_text = (
                '\n'.join(output_texts) if output_texts else f"Tool '{tool_name}' completed."
            )
            final_state = TaskState.failed if call_result.isError else TaskState.completed

            await task_updater.update_status(
                state=final_state,
                message=new_agent_text_message(final_text),
            )

        except Exception:
            logger.exception("Failed executing tool '%s'", tool_name)
            await task_updater.update_status(
                state=TaskState.failed,
                message=new_agent_text_message(f"Execution of tool '{tool_name}' failed."),
            )

    def _parse_tool_invocation(
        self, query: str, available_tools: dict[str, mcp_types.Tool]
    ) -> tuple[str | None, dict[str, Any]]:
        """Parse tool name and arguments from text or structured JSON."""
        stripped = query.strip()

        # 1. Direct JSON syntax
        tool_name, args = _parse_json_payload(stripped, available_tools)
        if tool_name:
            return tool_name, args

        # 2. CLI syntax
        tool_name, args = _parse_cli_syntax(stripped)
        if tool_name:
            return tool_name, args

        # 3. Function call syntax
        tool_name, args = _parse_function_call(stripped, available_tools)
        if tool_name:
            return tool_name, args

        # 4. Exact tool name search
        for name in available_tools:
            if name.lower() in stripped.lower():
                return name, {'query': stripped}

        return None, {}

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel task execution."""
        raise NotImplementedError('Cancellation is not supported for MCP tool executions.')
