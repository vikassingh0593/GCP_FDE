"""Correct code that the scanner must not report. Parsed only, never run."""
import logging
import os

from fastapi import Depends, FastAPI
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.memory import VertexAiMemoryBankService
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

LOGGER = logging.getLogger(__name__)
MODEL = os.environ["MODEL_ID"]
TABLE = os.environ["TABLE"]
INSTRUCTION = "User: {user:name?} Case: {current_case?} Literal: {{not_a_placeholder}}"
api = FastAPI()
specialist = RemoteA2aAgent(name="specialist", agent_card=os.environ["SPECIALIST_CARD_URL"], timeout=30)
mcp_tools = McpToolset(
    connection_params=StreamableHTTPConnectionParams(url=os.environ["MCP_SERVER_URL"]),
    tool_filter=["get_order"],
)


def verified_user():
    return "user"


@api.get("/me")
async def me(user=Depends(verified_user)):
    return {"user": user}


def lookup(order_id: str, tool_context) -> dict:
    """Return one order for the caller. Use it when the user names an order."""
    tool_context.state["user:region"] = "India"
    tool_context.state["temp:last_tool"] = "lookup"
    tool_context.state["current_case"] = order_id
    return {"status": "success", "data": {"order_id": order_id}}


def before_tool(tool, args, tool_context):
    return None


def build_store_service(kind):
    if kind == "a":
        return object()
    raise ValueError(f"Unknown backend: {kind}")


def save(memory_service, session, settings):
    query = f"SELECT id FROM {TABLE} JOIN {settings.other} USING (id)"
    LOGGER.info("saved %s", session.id)
    return memory_service.add_session_to_memory(session), query


agent = Agent(name="order_agent", model=MODEL, instruction=INSTRUCTION, tools=[lookup], before_tool_callback=before_tool)
