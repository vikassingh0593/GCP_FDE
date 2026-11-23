"""Orchestrator -> A2A -> Fulfilment Specialist, for real, on localhost: no cloud, no Gemini.

The specialist runs as a real A2A server (uvicorn in a thread, its own harness,
its hand-built Agent Card); the orchestrator calls it through RemoteA2aAgent.
Both use scripted models and canned BigQuery rows. This proves what no unit
test can: the correlation ID crosses the boundary (the specialist's harness
accepts the request and logs it under the orchestrator's ID), the reply
contract survives the trip, and the specialist's evidence IDs become citable
evidence on the orchestrator side.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
import uvicorn
from google.adk.sessions import InMemorySessionService
from google.genai import types

from common import config
from fakes import ORDER_ROWS, ScriptedModel, ago, call, fake_query_rows, last_responses, say

INVENTORY = {
    ("WH-BLR-01", "SKU-74512"): {"warehouse_id": "WH-BLR-01", "sku": "SKU-74512", "on_hand": 7, "reserved": 0,
                                 "available": 7, "snapshot_at": ago(minutes=10)},
    ("WH-DEL-01", "SKU-74512"): {"warehouse_id": "WH-DEL-01", "sku": "SKU-74512", "on_hand": 65, "reserved": 10,
                                 "available": 55, "snapshot_at": ago(minutes=12)},
}


def specialist_rows(sql, params=None, what="", timeout=30.0):
    """Canned BigQuery for the specialist's tools, picked by the tool name query_rows is given."""
    if what == "get_order_line":
        r = ORDER_ROWS["ORD-78421"]
        return [{k: r[k] for k in ("order_id", "order_type", "sku", "quantity", "warehouse_id", "status",
                                   "status_reason_code", "placed_at", "promised_delivery_at", "extracted_at")}]
    if what == "check_inventory":
        return [INVENTORY[("WH-BLR-01", "SKU-74512")]]
    if what == "find_stock_elsewhere":
        return [INVENTORY[("WH-DEL-01", "SKU-74512")]]
    return []


def specialist_answer(request):
    r = last_responses(request)
    inv = r["check_inventory"]
    return types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(
        name="set_model_response", args={
            "order_id": "ORD-78421", "verdict": "no", "reason": "true_shortage", "warehouse_id": "WH-BLR-01",
            "sku": "SKU-74512", "ordered": 40, "on_hand": 7, "reserved": 0, "available": 7,
            "inventory_freshness": inv["freshness"], "inventory_snapshot_at": inv["source_time"],
            "inventory_read_at": inv["read_at"], "alternatives": [{"warehouse_id": "WH-DEL-01", "available": 55}],
            "evidence_ids": [r["get_order_line"]["evidence_id"], inv["evidence_id"],
                             r["find_stock_elsewhere"]["evidence_id"]],
            "explanation": "7 available at WH-BLR-01 against 40 ordered.", "check_next": []}))])


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def specialist(monkeypatch):
    from fulfilment_specialist.fulfilment_agent import agent as spec
    from fulfilment_specialist.tools import inventory

    port = free_port()
    monkeypatch.setattr(config, "FULFILMENT_AGENT_PORT", port)
    monkeypatch.setattr(inventory, "query_rows", specialist_rows)
    model = ScriptedModel(steps=[
        call("get_order_line", order_id="ORD-78421"),
        call("check_inventory", warehouse_id="WH-BLR-01", sku="SKU-74512", required_quantity=40),
        call("find_stock_elsewhere", sku="SKU-74512", required_quantity=40, exclude_warehouse_id="WH-BLR-01"),
        specialist_answer,
    ])
    monkeypatch.setattr(spec.root_agent, "model", model)
    server = uvicorn.Server(uvicorn.Config(spec.build_a2a_app(), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "specialist did not start"
    yield {"port": port, "harness": spec.HARNESS, "model": model}
    server.should_exit = True
    thread.join(timeout=5)


def test_one_correlation_id_from_orchestrator_to_specialist_tools(specialist, monkeypatch):
    from orchestrator import runtime as runtime_module
    from orchestrator.tools import orders

    monkeypatch.setattr(orders, "query_rows", fake_query_rows({"orders": list(ORDER_ROWS.values())}))
    rt = runtime_module.Runtime(card_url=f"http://127.0.0.1:{specialist['port']}/.well-known/agent-card.json",
                                timeout=10, session_service=InMemorySessionService())

    def final(request):
        r = last_responses(request)
        fulfil = r["check_fulfilment"]
        assert fulfil["status"] == "ok", fulfil
        inv_id = next(i for i in fulfil["data"]["evidence_ids"] if i.startswith("EV-INV-"))
        return (f"OUTCOME: cause_named\nCAUSE: inventory_shortage\nFULFILABLE: no\n"
                f"ANSWER: 7 available against 40 ordered.\nOBSERVATIONS:\n- 7 available at WH-BLR-01 [{inv_id}]")

    rt.app.root_agent.model = ScriptedModel(steps=[call("get_order", order_id="ORD-78421"),
                                                   call("check_fulfilment", order_id="ORD-78421"), say(final)])

    async def go():
        s = await rt.create_session("analyst_e2e")
        return await rt.run_turn("analyst_e2e", s.id, "Investigate ORD-78421.")

    result = asyncio.run(go())
    assert result.header == {"outcome": "cause_named", "cause": "inventory_shortage", "fulfilable": "no"}

    orch = result.trace
    assert [t["outcome"] for t in orch["tools"]] == ["ok", "ok"]
    assert orch["invalid_citations"] == []                     # the specialist's evidence ID is citable here
    a2a = next(d for d in orch["details"] if d.get("a2a"))
    assert a2a["outcome"] == "ok" and a2a["verdict"] == "no"

    # The specialist's own harness accepted the request and traced it under the SAME correlation ID.
    spec = specialist["harness"].finished_trace(result.correlation_id)
    assert spec is not None, "specialist harness did not see the orchestrator's correlation ID"
    assert spec["user"] == "analyst_e2e" and spec["termination"] == "NORMAL"
    assert [t["tool"] for t in spec["tools"]] == ["get_order_line", "check_inventory", "find_stock_elsewhere",
                                                  "set_model_response"]
    # Every ID the specialist reported was returned by one of its tools, and arrives as known evidence.
    assert len(spec["cited_ids"]) == 3 and spec["invalid_citations"] == []
    assert set(spec["cited_ids"]) <= set(orch["evidence_ids"])


def test_invented_evidence_id_in_the_specialist_reply_is_flagged(specialist, monkeypatch):
    from orchestrator import runtime as runtime_module
    from orchestrator.tools import orders

    def invented(request):
        content = specialist_answer(request)
        content.parts[0].function_call.args["evidence_ids"] = ["EV-INV-WH-BLR-01/SKU-74512-abcdef"]
        return content
    specialist["model"].steps[-1] = invented

    monkeypatch.setattr(orders, "query_rows", fake_query_rows({"orders": list(ORDER_ROWS.values())}))
    rt = runtime_module.Runtime(card_url=f"http://127.0.0.1:{specialist['port']}/.well-known/agent-card.json",
                                timeout=10, session_service=InMemorySessionService())
    rt.app.root_agent.model = ScriptedModel(steps=[call("check_fulfilment", order_id="ORD-78421"),
                                                   say("OUTCOME: partial\nCAUSE: none")])

    async def go():
        s = await rt.create_session("analyst_e2e")
        return await rt.run_turn("analyst_e2e", s.id, "Can ORD-78421 be fulfilled?")

    result = asyncio.run(go())
    spec = specialist["harness"].finished_trace(result.correlation_id)
    assert spec["invalid_citations"] == ["EV-INV-WH-BLR-01/SKU-74512-abcdef"]
