"""The A2A boundary without a network: reply contract, trace forwarding, and the Agent Card's opacity."""

from __future__ import annotations

import json
from types import SimpleNamespace

from common.harness import RequestContext
from orchestrator.a2a_client import forward_trace_context, parse_reply

GOOD = {"order_id": "ORD-78421", "verdict": "no", "reason": "true_shortage", "evidence_ids": ["EV-INV-x-aaaaaa"],
        "explanation": "7 available, 40 ordered."}


def test_valid_reply_is_accepted_even_with_text_around_it():
    assert parse_reply(json.dumps(GOOD), "ORD-78421")["verdict"] == "no"
    assert parse_reply("Here you go:\n" + json.dumps(GOOD) + "\nDone.", "ORD-78421") is not None


def test_reply_that_breaks_the_contract_is_rejected():
    assert parse_reply("A2A request failed: connection refused", "ORD-78421") is None
    assert parse_reply(json.dumps({**GOOD, "verdict": "probably"}), "ORD-78421") is None
    assert parse_reply(json.dumps({**GOOD, "order_id": "ORD-11111"}), "ORD-78421") is None   # someone else's order
    assert parse_reply(json.dumps({k: v for k, v in GOOD.items() if k != "evidence_ids"}), "ORD-78421") is None


def test_correlation_id_is_forwarded_in_a2a_metadata():
    ctx = RequestContext.create(user="analyst_1", session_id="s_1")
    invocation = SimpleNamespace(run_config=SimpleNamespace(custom_metadata=ctx.to_metadata()))
    meta = forward_trace_context(invocation, None)
    assert meta["correlation_id"] == ctx.correlation_id and meta["user"] == "analyst_1"
    assert forward_trace_context(SimpleNamespace(run_config=SimpleNamespace(custom_metadata=None)), None) == {}


def test_agent_card_shows_one_skill_and_no_internal_tools():
    from starlette.testclient import TestClient
    from fulfilment_specialist.fulfilment_agent.agent import build_a2a_app

    with TestClient(build_a2a_app()) as client:
        card = client.get("/.well-known/agent-card.json").json()
    assert [s["id"] for s in card["skills"]] == ["fulfilment_check"]
    text = json.dumps(card)
    for internal in ("get_order_line", "check_inventory", "find_reservations", "find_stock_elsewhere", "INSTRUCTION"):
        assert internal not in text
    assert "verdict" in card["description"]                       # the reply contract is on the card


def test_specialist_never_imports_the_orchestrator():
    from conftest import ROOT
    for path in (ROOT / "fulfilment_specialist").rglob("*.py"):
        assert "orchestrator" not in "".join(l for l in path.read_text().splitlines(True)
                                            if l.startswith(("import", "from"))), path
