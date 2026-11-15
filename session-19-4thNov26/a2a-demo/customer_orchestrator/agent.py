"""Customer-facing ADK agent consuming a remote specialist through A2A.

Run after the specialist:
    adk web 02_customer_orchestrator --port "$ORCHESTRATOR_PORT"

Key point:
    This project never imports the specialist's Python tools.
"""
from __future__ import annotations
import os
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

#Resolve the independent agent through its discoverable Agent Card.
fulfilment_specialist=RemoteA2aAgent(
    name="fulfilment_specialist",
    description=(
        "Remote specialist for authoritative order fulfilment investigations, "
        "including order status, warehouse, SKU, inventory and feasibility."
    ),
    agent_card="http://localhost:8001/.well-known/agent-card.json",
    use_legacy=False,
)

# The orchestrator owns the conversation and delegates domain work.
root_agent=Agent(
    name="customer_operations_orchestrator",
    model="gemini-2.5-flash",
    description="Customer operations orchestrator using an independent A2A fulfilment specialist.",
    instruction="""
You are the Customer Operations Orchestrator.
You own the customer conversation, but not authoritative fulfilment facts.
Delegate to fulfilment_specialist for order fulfilment, assigned warehouse,
inventory availability, and whether an order can be fulfilled.
Do not invent specialist-owned facts.
For unrelated general conversation, answer directly.
When the specialist returns, preserve the important evidence and explain it clearly.
""",
   sub_agents=[fulfilment_specialist],
)
