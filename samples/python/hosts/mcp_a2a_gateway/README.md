# MCP-to-A2A Dynamic Protocol Gateway

A dynamic protocol gateway host that bridges Anthropic's **Model Context Protocol (MCP)** and Google's **Agent2Agent (A2A)** protocol.

The gateway connects to any standard MCP server (`stdio` or `sse`), introspects its tool catalog (`tools/list`), dynamically generates an A2A `AgentCard` advertising those tools as `AgentSkill` declarations, and hosts an A2A JSON-RPC server. Incoming A2A tasks are routed to the underlying MCP tools, with outputs serialized into A2A `Artifact` and `Task` lifecycle events.

```
+------------------+         A2A Protocol (JSON-RPC)         +-------------------------------+
|  A2A Client /    | --------------------------------------> |   MCP-to-A2A Gateway Host     |
|  Super-Agent     | <-------------------------------------- |   (Starlette / Uvicorn Server)|
+------------------+     AgentCard, TaskState & Artifacts    +---------------+---------------+
                                                                             |
                                                               MCP Protocol  | (stdio / SSE)
                                                                             v
                                                             +-------------------------------+
                                                             |       Target MCP Server       |
                                                             |  (SQLite, Postgres, FS, etc.) |
                                                             +-------------------------------+
```

---

## Key Capabilities

* **Dynamic AgentCard Synthesis**: Translates MCP tool schemas into A2A `AgentSkill` entries with parameter hints and tag metadata.
* **Dual Transport Support**: Connects to local subprocess MCP servers via `stdio` or remote microservices via `sse`.
* **Structured Artifact Emission**: Serializes tool return data into structured A2A `Artifact` objects (`TextPart`, `DataPart`) alongside task state transitions (`WORKING` -> `COMPLETED`).
* **Self-Contained Reference Server**: Includes a zero-dependency sample FastMCP server (`sample_mcp_server.py`) offering database, financial calculation, and system diagnostics tools.

---

## Architecture & Package Structure

* **`mcp_client.py`**: Manages MCP client session lifecycles, transport initialization (`stdio` / `sse`), and tool invocations.
* **`card_generator.py`**: Translates MCP tool schemas into an A2A `AgentCard`.
* **`executor.py`**: Implements `McpGatewayExecutor` (`AgentExecutor`) to route incoming A2A messages to MCP tools and emit A2A `Artifact` objects.
* **`server.py`**: Builds the Starlette ASGI application hosting the A2A endpoint.
* **`sample_mcp_server.py`**: Embedded FastMCP server providing reference tools for testing.
* **`__main__.py`**: CLI entry point to launch the gateway with configurable parameters.
* **`test_client.py`**: Demonstration client resolving the gateway's `AgentCard` and executing tasks.
* **`test_gateway.py`**: Automated integration test suite validating end-to-end communication.

---

## Quick Start

### 1. Start the Gateway with the Built-In Reference MCP Server

From the repository root or Python workspace directory:

```bash
cd samples/python/hosts/mcp_a2a_gateway
uv run python -m samples.python.hosts.mcp_a2a_gateway --port 9090
```

The gateway automatically starts the built-in reference MCP server over `stdio`, dynamically builds the `AgentCard`, and starts listening on `http://127.0.0.1:9090`.

### 2. Connect via the Sample A2A Client

In a separate terminal window:

```bash
cd samples/python/hosts/mcp_a2a_gateway
uv run python test_client.py --agent-url http://127.0.0.1:9090
```

You can pass custom queries or tool commands:

```bash
uv run python test_client.py --query 'call query_database {"sql": "SELECT * FROM products WHERE price > 200"}'
```

```bash
uv run python test_client.py --query 'call calculate_financial_roi {"investment": 5000, "annual_gain": 1200, "years": 3}'
```

---

## Connecting External MCP Servers

### Stdio Subprocess (e.g., SQLite / Filesystem MCP Server)

```bash
uv run python -m samples.python.hosts.mcp_a2a_gateway \
    --stdio-command "npx -y @modelcontextprotocol/server-filesystem /tmp" \
    --port 9090 \
    --name "Filesystem A2A Gateway"
```

### Remote SSE Transport

```bash
uv run python -m samples.python.hosts.mcp_a2a_gateway \
    --sse-url "http://remote-mcp-server:8000/sse" \
    --port 9090 \
    --name "Remote Enterprise MCP Gateway"
```

---

## Running Automated Tests

Run the full end-to-end integration and unit test suite:

```bash
cd samples/python/hosts/mcp_a2a_gateway
uv run pytest -v test_gateway.py
```
