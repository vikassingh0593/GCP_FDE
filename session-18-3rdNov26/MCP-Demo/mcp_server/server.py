from __future__ import annotations
import os

from mcp.server.fastmcp import FastMCP

from mcp_server.tools import check_inventory, get_order, get_customer

SERVER_NAME = "enterprise-operations"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001

mcp = FastMCP(
    SERVER_NAME,
    host=os.environ.get("MCP_HOST", DEFAULT_HOST),
    port=int(os.environ.get("MCP_PORT", DEFAULT_PORT)),
)

mcp.tool()(get_order)
mcp.tool()(check_inventory)
mcp.tool()(get_customer)


def main() -> None:

    endpoint = os.getenv(
        "MCP_SERVER_URL",
        f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/mcp",
    )

    print("Enterprise Operations MCP Server")
    print(f"Server name : {SERVER_NAME}")
    print(f"MCP endpoint: {endpoint}")
    print("Tools       : get_order, check_inventory, get_customer")
    print("Press Ctrl+C to stop.\n")

    mcp.run(transport = "streamable-http")


if __name__ == "__main__":
    main()