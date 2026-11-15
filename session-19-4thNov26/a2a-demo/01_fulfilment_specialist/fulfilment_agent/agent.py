from __future__ import annotations
import os
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent
from .tools import check_inventory, get_order


root_agent = Agent(
    name =  "fulfilment_specialist",
    model = os.getenv("MODEL_ID","gemini-2.5-flash"),
    description=(
        "Specialist agent for investigating whether enterprise orders can be "
        "fulfilled from their assigned warehouse using order and inventory evidence."
    ),
    instruction="""
        You are the Enterprise Fulfilment Specialist.
        For a fulfilment investigation:
        1. Retrieve the authoritative order.
        2. If absent, stop and say evidence is unavailable.
        3. Use the returned warehouse, SKU and required quantity.
        4. Check inventory for those exact identifiers.
        5. Compare required and available quantities.
        6. Return a concise evidence-based specialist conclusion.
        Never invent order, warehouse, SKU or quantity data.
        """,
    tools = [get_order, check_inventory]
    )


a2a_app = to_a2a(
    root_agent,
    host="127.0.0.1",
    port=int(os.getenv("FULFILMENT_AGENT_PORT","8001")),
)