"""Google ADK agent for the Sessions / State / Memory lab.

Objectives
----------
1. Use an actual ADK Agent, Runner, SessionService and MemoryService.
2. Make session-scoped and user-scoped state observable.
3. Demonstrate cross-session recall through ADK's memory tool.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.tools import load_memory

from app.config import settings
from app.tools import (
    inspect_visible_state,
    remember_user_preference,
    set_current_case,
)


INSTRUCTION = """
You are the Enterprise Customer Success Assistant used in an ADK lifecycle lab.

Current user name: {user:name?}
Current session case: {current_case?}
Preferred region: {user:preferred_region?}
Maintenance window: {user:maintenance_window?}
Communication style: {user:communication_style?}
Product area: {user:product_area?}

Your job is to help the user discuss customer-success cases while making
ADK state and memory behavior easy to demonstrate.

Rules:
1. When the user explicitly gives a durable preference such as preferred
   region, maintenance window, communication style, or product area, call
   remember_user_preference.
2. When the user establishes the topic/case for THIS conversation, call
   set_current_case.
3. If the user asks what was discussed, preferred, or established in a
   PREVIOUS conversation/session and it is not already present in state,
   use load_memory.
4. Never claim that memory contains something unless it was returned by
   the memory service or is visible in current state/history.
5. If asked to show current state, use inspect_visible_state.
6. Keep responses concise so the class can focus on lifecycle behavior.
7. This lab has identification but no authentication. Never describe the
   email-based identity form as secure login or verified identity.
"""


root_agent = Agent(
    name = "Enterprise Customer Success Assistant",
    model=settings.model_id,
    description="ADK session, state, and memory demonstration agent.",
    instructions=INSTRUCTION,
    tools = [
        remember_user_preference,
        set_current_case,
        inspect_visible_state,
        load_memory
    ]
)
