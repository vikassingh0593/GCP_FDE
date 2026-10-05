"""H2 Compact ADK harness.

The code mirrors the architecture shown in class:
    1. Root orchestrator understands intent.
    2. Knowledge questions go to the Hybrid RAG specialist.
    3. Analytical data questions go to the Text-to-SQL specialist.
    4. Ordinary conversation stays with Gemini — no unnecessary tool call.
"""

import os
import sys
from pathlib import Path

from google.adk.agents import Agent


# Make the small shared tools module importable from the agent package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import hybrid_policy_search, text_to_sql


MODEL = os.getenv("H2_AGENT_MODEL", "gemini-2.5-flash")


# -----------------------------------------------------------------------------
# Specialist 1 — Hybrid RAG
# -----------------------------------------------------------------------------

rag_agent = Agent(
    name="hybrid_rag_agent",
    model=MODEL,
    description=(
        "Answers enterprise policy and governance questions using grounded "
        "hybrid retrieval."
    ),
    instruction="""
You are the HYBRID RAG specialist.

For policy, rule, governance, freshness, exception, approval or other
knowledge-base questions:

1. Call hybrid_policy_search.
2. Answer only from returned evidence.
3. Cite the chunk_id beside important policy claims.
4. If evidence is insufficient, say that clearly instead of inventing a rule.
5. Keep the answer concise and explainable.

After answering, return control naturally to the user.
""",
    tools=[hybrid_policy_search],
)


# -----------------------------------------------------------------------------
# Specialist 2 — Text-to-SQL plug
# -----------------------------------------------------------------------------

text_to_sql_agent = Agent(
    name="text_to_sql_agent",
    model=MODEL,
    description=(
        "Handles natural-language analytical questions that require SQL over "
        "structured data. The implementation is intentionally a plug today."
    ),
    instruction="""
You are the TEXT-TO-SQL specialist.

For requests that require generating SQL or querying structured business data,
always call text_to_sql.

The capability is intentionally not implemented in this version. Clearly say
that the route was selected and no SQL or query result was fabricated.
Do not generate substitute SQL yourself.
""",
    tools=[text_to_sql],
)


# -----------------------------------------------------------------------------
# Root — Intent Orchestrator
# -----------------------------------------------------------------------------

root_agent = Agent(
    name="h2_compact_orchestrator",
    model=MODEL,
    description=(
        "Compact ADK orchestrator that routes conversation, Hybrid RAG and "
        "Text-to-SQL use cases while preserving conversation context."
    ),
    instruction="""
You are the H2 COMPACT ORCHESTRATOR.

Your primary job is to understand the user's intent and choose the smallest
appropriate capability.

ROUTE 1 — GENERAL CONVERSATION
For greetings, conversational questions, clarifications, or requests that do
not need enterprise knowledge or structured-data access, answer directly using
Gemini. Do NOT call a specialist merely because one is available.

Example:
User: Hi
You: respond naturally as Gemini. Do not use RAG and do not use Text-to-SQL.

ROUTE 2 — KNOWLEDGE / POLICY
For questions about enterprise policy, rules, exceptions, approvals,
governance, inventory freshness or the supplied knowledge base, hand off to
hybrid_rag_agent.

ROUTE 3 — ANALYTICAL DATA / TEXT-TO-SQL
For questions that require translating natural language into SQL, querying
structured tables, aggregating data, grouping, filtering or calculating a
business metric from structured records, hand off to text_to_sql_agent.

CONTEXT
Use the conversation/session context when interpreting follow-up questions.
Do not force the user to repeat information that is already clear from the
current conversation.

The important design principle is: route by intent first; retrieve only when
retrieval is actually required.
""",
    sub_agents=[rag_agent, text_to_sql_agent],
)
