import asyncio
import json
import logging

from uuid import uuid4

import click
import httpx

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import (
    Message,
    Task,
    TextPart,
)
from a2a.utils.message import get_message_text


logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('mcp_a2a_client')


@click.command()
@click.option(
    '--agent-url',
    default='http://127.0.0.1:9090',
    help='Base URL of the MCP-to-A2A Gateway.',
)
@click.option(
    '--query',
    default='call query_database {"sql": "SELECT name, price, stock FROM products WHERE price >= 100"}',
    help='Query or tool execution command to send.',
)
def main(agent_url: str, query: str) -> None:
    """A2A Client demonstrating task delegation to the MCP-to-A2A Dynamic Gateway."""

    async def run_client() -> None:
        async with httpx.AsyncClient(timeout=30) as http_client:
            logger.info('Resolving AgentCard from %s...', agent_url)
            resolver = A2ACardResolver(
                httpx_client=http_client,
                base_url=agent_url,
            )
            card = await resolver.get_agent_card()

            print('\n======================================================')
            print('          RESOLVED DYNAMIC A2A AGENT CARD')
            print('======================================================')
            print(f'Name        : {card.name}')
            print(f'Description : {card.description}')
            print(f'Version     : {card.version}')
            print(f'URL         : {card.url}')
            print('\nExposed Skills / Tools:')
            for skill in card.skills:
                print(f'  • [{skill.name}] - {skill.description}')
            print('======================================================\n')

            factory = ClientFactory(ClientConfig(httpx_client=http_client))
            a2a_client = factory.create(card)

            message = Message(
                role='user',
                parts=[TextPart(text=query)],
                message_id=str(uuid4()),
            )

            logger.info('Sending A2A Task to Gateway: "%s"', query)
            events = [event async for event in a2a_client.send_message(message)]

            final_event = events[-1]
            result = final_event[0] if isinstance(final_event, tuple) else final_event

            print('\n======================================================')
            print('               A2A EXECUTION RESPONSE')
            print('======================================================')
            if isinstance(result, Task):
                print(f'Task ID    : {result.id}')
                print(f'Task State : {result.status.state}')
                print(f'Message    : {get_message_text(result.status.message)}')
                if result.artifacts:
                    print('\nReturned Artifacts:')
                    for idx, art in enumerate(result.artifacts):
                        print(f'  Artifact #{idx + 1} ({art.name}):')
                        for part in art.parts:
                            if hasattr(part.root, 'text'):
                                print(f'    - Text: {part.root.text}')
                            elif hasattr(part.root, 'data'):
                                print(f'    - Data: {json.dumps(part.root.data, indent=2)}')
            elif isinstance(result, Message):
                print(f'Message    : {get_message_text(result)}')
            print('======================================================\n')

    asyncio.run(run_client())


if __name__ == '__main__':
    main()
