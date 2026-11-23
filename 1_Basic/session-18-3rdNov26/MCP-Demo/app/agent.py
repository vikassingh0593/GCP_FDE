from __future__ import annotations
import os

from google.adk.agents import Agent

from google.adk.tools.mcp_tool import (
    McpToolset,
    StreamableHTTPConnectionParams,
)

MODEL_ID = os.getenv("MODEL_ID", "gemini-2.5-flash")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", 
                           "http://127.0.0.1:8001/mcp")

operations_mcp_tools = McpToolset(
    connection_params = StreamableHTTPConnectionParams(
        url = MCP_SERVER_URL,
    )
)

root_agent = Agent(
    name = "Enterprise_operations_agent",
    model = MODEL_ID,
    description = (
        "Investigates enterprise orders using capabilities exposed by the "
        "Enterprise Operations MCP Server."
    ),
    instruction="""
You are an enterprise operations assistant.

Use the MCP-provided tools whenever authoritative order, inventory, or customer
information is required.

Rules:
1. Never invent order, customer, warehouse, SKU, quantity, or inventory data.
2. Obtain identifiers from authoritative tool results whenever possible.
3. Check inventory only when fulfilment information is relevant.
4. Retrieve customer information only when it is relevant to the question.
5. Treat NOT_FOUND as missing evidence, not as permission to guess.
6. Separate observed tool evidence from any inference you make.
7. Keep the final response concise and evidence-based.
""".strip(),
    tools = [
       operations_mcp_tools 
    ]
)