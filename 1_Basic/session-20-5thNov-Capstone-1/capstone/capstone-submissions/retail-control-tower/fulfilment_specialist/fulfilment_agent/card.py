"""The Agent Card: what the specialist advertises to callers.

ADK can build a card automatically, but that card lists every internal tool
as a skill (get_order_line, check_inventory, ...). That leaks the internals
the A2A boundary is meant to hide, and a caller could start depending on
them. So the card is built here with ONE business skill: the fulfilment check.

Visible on the card: name, description (with the reply fields), endpoint,
capabilities, the one skill and its examples.
Not visible: instructions, tools, data sources, model, reasoning steps.

Check it:  curl -s "$FULFILMENT_AGENT_CARD_URL" | python -m json.tool
"""

from __future__ import annotations

from common import config

SKILL_ID = "fulfilment_check"
VERSION = "1.0.0"


def build_agent_card():
    # _compat builds a card that is valid for the installed a2a-sdk (0.3 pydantic or 1.x proto). It is a
    # private ADK module, so versions are pinned in requirements.lock and test_a2a_offline.py serves
    # this card: an ADK upgrade that breaks it fails the tests, not the demo.
    from google.adk.a2a import _compat

    from fulfilment_specialist.fulfilment_agent.agent import DESCRIPTION, SERVICE

    skill = _compat.build_agent_skill(
        id=SKILL_ID,
        name="Fulfilment check",
        description=("Can the order's assigned warehouse fulfil it now? Returns verdict, reason, stock "
                     "figures with snapshot time and freshness, reservations, re-route options and "
                     "evidence IDs as one JSON object. Read-only."),
        tags=["fulfilment", "inventory", "read-only"],
        examples=['{"task": "fulfilment_check", "order_id": "ORD-78421"}'],
    )
    return _compat.build_agent_card(
        name=SERVICE,
        description=DESCRIPTION,
        version=VERSION,
        url=f"http://{config.FULFILMENT_AGENT_HOST}:{config.FULFILMENT_AGENT_PORT}/",
        protocol_binding="JSONRPC",
        skills=[skill],
        capabilities={"streaming": True},
    )
