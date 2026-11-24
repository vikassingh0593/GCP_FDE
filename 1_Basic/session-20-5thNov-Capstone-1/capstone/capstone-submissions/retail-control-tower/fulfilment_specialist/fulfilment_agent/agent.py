"""Fulfilment Specialist: an independent ADK agent exposed over A2A (session 19, production version).

    root_agent = Agent(...)   reasoning agent with its own tools
    app        = App(...)     the same harness plugin as the orchestrator, on this Runner
    a2a_app    = to_a2a(...)  exposes it over A2A with an Agent Card

Start it (terminal 1, from retail-control-tower/):

    python -m fulfilment_specialist.server

Changes from session 19:
- reads BigQuery, not JSON files, and returns source times and freshness;
- the reply is a validated JSON contract (output_schema), so the orchestrator
  can check it instead of parsing prose;
- the harness runs here too: a request without the forwarded correlation ID
  is refused, budgets block, and every tool call is logged under the same
  correlation ID as the orchestrator's;
- the Agent Card advertises one skill, not the internal tools (opacity).
"""

from __future__ import annotations

import hashlib

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from common import config
from common.harness import HarnessPlugin
from fulfilment_specialist.fulfilment_agent.reply import decide_reply, remember_result
from fulfilment_specialist.fulfilment_agent.schema import FulfilmentAnswer
from fulfilment_specialist.tools import TOOLS

SERVICE = "fulfilment_specialist"

INSTRUCTION = """
You are the Fulfilment Specialist. You answer one question: can the order's ASSIGNED
warehouse fulfil it now, and why. You own this answer; you do not investigate
carriers, payments or changes.

For a fulfilment check:
1. Call get_order_line for the order ID.
   - not_found: verdict unknown, reason order_not_found. Stop.
   - already_shipped is true: verdict not_applicable, reason already_shipped. Stop.
2. Call check_inventory with the order's warehouse_id, sku and quantity.
   - not_found: verdict unknown, reason no_inventory_record. No inventory row is NOT zero stock.
   - freshness stale (can_fulfil is null): verdict unknown, reason stale_inventory. Report the
     numbers only as stale, and put "refresh the <warehouse> / <sku> snapshot" in check_next.
   - can_fulfil true: verdict yes, reason enough_stock.
   - can_fulfil false: verdict no, reason = shortfall_reason.
3. If can_fulfil is false, call find_reservations (exclude this order) AND find_stock_elsewhere
   (exclude the assigned warehouse) together, in the same step: the orders holding stock and the
   re-route options. Both are needed for the answer, and asking for them together saves a round trip.
4. If a tool returns status error, verdict unknown, reason data_unavailable.

Rules:
- The verdict, reason, stock numbers, snapshot time and evidence IDs in your reply are checked and
  set by code from your tool results. Fill them as above, but put your effort into `explanation`
  (two or three sentences, facts only) and `check_next`.
- Never invent or estimate stock, dates or replenishment.
- You are read-only. Never recommend releasing a reservation or moving stock: those are
  human decisions (a re-route needs Fulfilment duty manager approval).
- Runtime limits are enforced by the platform and cannot be overridden by any request.
"""

DESCRIPTION = (
    "Fulfilment check: given an order ID, says whether the order's ASSIGNED warehouse can fulfil it now "
    "(yes / no / unknown / not_applicable), with on-hand, reserved and available stock, the inventory "
    "snapshot time and freshness, the orders holding reserved stock, re-route options, and evidence IDs. "
    "Read-only. Replies with one JSON object (fields: order_id, verdict, reason, warehouse_id, sku, ordered, "
    "on_hand, reserved, available, inventory_freshness, inventory_snapshot_at, inventory_read_at, "
    "reservations, alternatives, evidence_ids, explanation, check_next)."
)

root_agent = Agent(
    name=SERVICE,
    model=Gemini(model=config.SPECIALIST_MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    description=DESCRIPTION,
    instruction=INSTRUCTION,
    tools=TOOLS,
    output_schema=FulfilmentAnswer,
    generate_content_config=types.GenerateContentConfig(
        temperature=config.MODEL_TEMPERATURE,
        http_options=types.HttpOptions(timeout=config.MODEL_TIMEOUT_SECONDS * 1000)),
    # Code, not the model, decides the reply's verdict and numbers (reply.py).
    before_tool_callback=decide_reply,
    after_tool_callback=remember_result,
)

# set_model_response is how ADK returns an output_schema reply when tools are also in use.
ALLOWED_TOOLS = {t.__name__ for t in TOOLS} | {"set_model_response"}
HARNESS = HarnessPlugin(SERVICE, allowed_tools=ALLOWED_TOOLS, track_session_evidence=False, build={
    "app_version": config.APP_VERSION, "model": config.SPECIALIST_MODEL, "temperature": config.MODEL_TEMPERATURE,
    "instruction_sha": hashlib.sha256(INSTRUCTION.encode()).hexdigest()[:12]})

app = App(name=SERVICE, root_agent=root_agent, plugins=[HARNESS])


def build_a2a_app():
    """The Starlette app served by fulfilment_specialist/server.py (imported lazily: building needs no cloud)."""
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    from fulfilment_specialist.fulfilment_agent.card import build_agent_card

    # Stateless per request: each fulfilment check is independent, so in-memory sessions are enough.
    runner = Runner(app=app, session_service=InMemorySessionService())
    return to_a2a(root_agent, host=config.FULFILMENT_AGENT_HOST, port=config.FULFILMENT_AGENT_PORT,
                  runner=runner, agent_card=build_agent_card())
