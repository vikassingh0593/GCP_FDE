"""Planted mistakes for the scanner test. Parsed only, never run."""
import os
import requests

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService

INSTRUCTION = "User: {user:name} Region: {users:region?}"
password = "hunter2hunter2"
api = FastAPI()
api.add_middleware(CORSMiddleware, allow_origins=["*"])
sessions = InMemorySessionService()
memories = InMemoryMemoryService()
specialist = RemoteA2aAgent(name="specialist", agent_card="http://localhost:8001/.well-known/agent-card.json")
mcp_tools = McpToolset(connection_params=StreamableHTTPConnectionParams(url="http://127.0.0.1:8001/mcp"))


def lookup(order_id: str, user_id: str, tool_context) -> dict:
    tool_context.state[f"users:{order_id}"] = "x"
    try:
        return requests.get("https://example.com").json()
    except Exception:
        pass


def build_store_service(kind):
    if kind == "a":
        return object()


def fetch(client, region):
    return client.query(f"SELECT * FROM t WHERE region = '{region}'")


def run(text, runtime, email):
    print(email)
    eval(text)
    runtime.session_service_create_session()
    runtime.memory_service.save_session_to_memory(None)
    raise HTTPException(status_code=500, detail="failed")


def handle(exc):
    return JSONResponse(content={"detail": f"boom: {exc}"})


RANKING_MODEL = "semantic-ranker-default@latest"   # KN-24: moves without a code change

agent = Agent(name="Bad Name", model="gemini-2.5-flash", instructions=INSTRUCTION, tools=[lookup])
