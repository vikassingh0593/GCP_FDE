"""Orchestrator and specialist tools on canned BigQuery rows: the planted facts come out right."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from common import results
from fakes import ago


def rows(*items):
    return lambda sql, params=None, what="", timeout=30.0: [dict(i) for i in items]


# ----------------------------------------------------------------------------- orchestrator

def test_get_order_returns_no_customer_details_and_sets_the_current_order(monkeypatch):
    from orchestrator.tools import orders
    monkeypatch.setattr(orders, "query_rows", rows({
        "order_id": "ORD-78436", "order_type": "B2C", "sku": "SKU-96140", "quantity": 2, "warehouse_id": "WH-DEL-01",
        "status": "ON_HOLD", "status_reason_code": "PAY-H201", "payment_status": "CREDIT_HOLD", "carrier": None,
        "tracking_number": None, "placed_at": ago(hours=26), "promised_delivery_at": ago(hours=2),
        "last_updated_at": ago(hours=24), "extracted_at": ago(minutes=5)}))
    ctx = SimpleNamespace(state={})
    out = orders.get_order("ord-78436", ctx)
    assert out["status"] == "ok" and out["freshness"] == "fresh"
    data = out["data"]
    assert not {"customer_name", "customer_phone", "shipping_address"} & set(data)
    assert data["hours_since_status_change"] == 24.0 and data["overdue"] and data["hours_overdue"] == 2.0
    assert ctx.state["current_order_id"] == "ORD-78436"


def test_get_order_not_found_and_bad_input(monkeypatch):
    from orchestrator.tools import orders
    monkeypatch.setattr(orders, "query_rows", rows())
    assert orders.get_order("ORD-99999", SimpleNamespace(state={}))["status"] == "not_found"
    assert orders.get_order("78421; DROP TABLE", SimpleNamespace(state={}))["error_type"] == "invalid_argument"


def test_carrier_events_show_late_event_and_missing_pickup(monkeypatch):
    from orchestrator.tools import events
    base = {"carrier": "Blue Dart", "tracking_number": "BD1", "exception_code": None, "location": "x"}
    monkeypatch.setattr(events, "query_rows", rows(
        {**base, "event_id": "CE-1", "event_code": "MANIFESTED", "description": "label", "event_at": ago(hours=50),
         "received_at": ago(hours=50)},
        {**base, "event_id": "CE-2", "event_code": "EXCEPTION", "exception_code": "WX-HOLD", "description": "rain",
         "event_at": ago(hours=20), "received_at": ago(hours=14)}))
    data = events.get_carrier_events("ORD-78433")["data"]
    assert data["latest_exception_code"] == "WX-HOLD" and data["has_pickup"] is False
    assert data["events"][1]["late_event"] and data["events"][1]["feed_lag_hours"] == 6.0


def test_before_after_comparison_matches_s6(monkeypatch):
    from orchestrator.tools import events
    change = {"change_id": "CHG-2311", "changed_at": ago(hours=20), "scope": "WH-BOM-01",
              "description": "rule set v2", "changed_by": "fulfilment-config-team"}
    order_rows = [
        {"order_id": "ORD-78446", "status": "SHIPPED", "status_reason_code": None, "placed_at": ago(hours=30)},
        {"order_id": "ORD-78447", "status": "SHIPPED", "status_reason_code": None, "placed_at": ago(hours=26)},
    ] + [{"order_id": f"ORD-7845{i}", "status": "ALLOCATION_PENDING", "status_reason_code": "ALLOC-E107",
          "placed_at": ago(hours=h)} for i, h in zip(range(4), (18, 15, 11, 6))] + [
        {"order_id": "ORD-78499", "status": "ALLOCATION_PENDING", "status_reason_code": "ALLOC-E101",
         "placed_at": ago(hours=4)}]          # a shortage after the change: not the change's failure
    order_rows = [dict(o, extracted_at=ago(minutes=5)) for o in order_rows]
    answers = iter([[change], order_rows])
    monkeypatch.setattr(events, "query_rows", lambda *a, **k: next(answers))
    monkeypatch.setattr(events, "change_runbook", lambda: ({"status": "ok", "results": []}, None))
    data = events.compare_before_after_change("CHG-2311")["data"]
    assert data["pattern"] == "consistent_with_change"
    assert data["before"]["failed_count"] == 0 and data["after"]["failed_count"] == 4
    assert data["reason_code_compared"] == "ALLOC-E107" and "ORD-78499" not in data["after"]["failed"]


def _one_change(events, monkeypatch):
    change = {"change_id": "CHG-2311", "changed_at": ago(hours=20), "scope": "WH-BOM-01",
              "description": "rule set v2", "changed_by": "fulfilment-config-team"}
    rows = [{"order_id": "ORD-78446", "status": "SHIPPED", "status_reason_code": None,
             "placed_at": ago(hours=30), "extracted_at": ago(minutes=5)}]
    answers = iter([[change], rows])
    monkeypatch.setattr(events, "query_rows", lambda *a, **k: next(answers))


def test_before_after_carries_the_change_runbook_found_by_tags_not_id(monkeypatch):
    """Run 5: the model's own query missed the change runbook. Code fetches it, by register tags."""
    from orchestrator.retrieval import search as search_module
    from orchestrator.tools import events
    _one_change(events, monkeypatch)
    asked = {}

    def fake_search(query, **filters):
        asked.update(filters, query=query)
        return {"status": "ok", "evidence_id": "EV-KNW-abc-123456",
                "data": {"results": [{"doc_id": "RB-CHG-006", "version": 1, "evidence_id": "EV-DOC-RB-CHG-006@v1-1"},
                                     {"doc_id": "X", "version": 1}, {"doc_id": "Y", "version": 1}]},
                "_trace": {"docs": ["RB-CHG-006@v1"]}}
    monkeypatch.setattr(search_module, "search", fake_search)

    out = events.compare_before_after_change("CHG-2311")
    assert asked["doc_type"] == "runbook" and asked["exception_type"] == "recent_change"
    assert "RB-CHG" not in asked["query"]                     # searched by text and tags, never by ID
    runbook = out["data"]["runbook"]
    assert runbook["status"] == "ok" and len(runbook["results"]) == events.CHANGE_RUNBOOK_CARDS
    assert out["_trace"]["docs"] == ["RB-CHG-006@v1"]         # the eval and the trace see what was retrieved
    assert "EV-DOC-RB-CHG-006@v1-1" in results.collect_evidence_ids(out)   # citable


def test_before_after_still_answers_when_the_runbook_search_fails(monkeypatch):
    from orchestrator.retrieval import search as search_module
    from orchestrator.tools import events
    _one_change(events, monkeypatch)

    def broken(query, **filters):
        raise RuntimeError("BigQuery down")
    monkeypatch.setattr(search_module, "search", broken)
    out = events.compare_before_after_change("CHG-2311")
    assert out["status"] == "ok" and out["data"]["pattern"] == "insufficient_before_group"
    assert out["data"]["runbook"]["status"] == "error" and out["_trace"]["docs"] == []


def test_before_after_needs_a_before_group(monkeypatch):
    from orchestrator.tools import events
    change = {"change_id": "CHG-1", "changed_at": ago(hours=20), "scope": "WH-BOM-01", "description": "", "changed_by": "x"}
    answers = iter([[change], [{"order_id": "ORD-1", "status": "ALLOCATION_PENDING", "status_reason_code": "X",
                                "placed_at": ago(hours=2), "extracted_at": ago(minutes=5)}]])
    monkeypatch.setattr(events, "query_rows", lambda *a, **k: next(answers))
    monkeypatch.setattr(events, "change_runbook", lambda: ({"status": "ok", "results": []}, None))
    assert events.compare_before_after_change("CHG-0001")["data"]["pattern"] == "insufficient_before_group"


# ----------------------------------------------------------------------------- specialist

def _inv(on_hand, reserved, available, minutes_old):
    return {"warehouse_id": "WH-BLR-01", "sku": "SKU-20417", "on_hand": on_hand, "reserved": reserved,
            "available": available, "snapshot_at": ago(minutes=minutes_old)}


@pytest.mark.parametrize("row,qty,can,reason", [
    (_inv(7, 0, 7, 10), 40, False, "true_shortage"),          # S1
    (_inv(60, 58, 2, 10), 10, False, "reserved_stock"),        # S11 / S2
    (_inv(80, 10, 70, 10), 2, True, None),                     # S4
    (_inv(20, 18, 2, 2 * 24 * 60), 6, None, None),             # S7: stale -> unknown, never yes/no
])
def test_check_inventory_verdicts(monkeypatch, row, qty, can, reason):
    from fulfilment_specialist.tools import inventory
    monkeypatch.setattr(inventory, "query_rows", rows(row))
    data = asyncio.run(inventory.check_inventory("WH-BLR-01", "SKU-20417", qty))["data"]
    assert data["can_fulfil"] is can and data["shortfall_reason"] == reason


def test_no_inventory_row_is_not_zero_stock(monkeypatch):
    from fulfilment_specialist.tools import inventory
    monkeypatch.setattr(inventory, "query_rows", rows())
    out = asyncio.run(inventory.check_inventory("WH-DEL-01", "SKU-30982", 2))          # S8
    assert out["status"] == "not_found" and "not the same as zero stock" in out["message"]


def test_specialist_order_line_has_no_customer_or_payment_fields(monkeypatch):
    from fulfilment_specialist.tools import inventory
    monkeypatch.setattr(inventory, "query_rows", rows({
        "order_id": "ORD-78421", "order_type": "B2B", "sku": "SKU-74512", "quantity": 40, "warehouse_id": "WH-BLR-01",
        "status": "ALLOCATION_PENDING", "status_reason_code": "ALLOC-E101", "placed_at": ago(hours=48),
        "promised_delivery_at": ago(hours=4), "extracted_at": ago(minutes=5)}))
    data = asyncio.run(inventory.get_order_line("ORD-78421"))["data"]
    assert not {"customer_name", "customer_phone", "shipping_address", "payment_status"} & set(data)
    assert data["already_shipped"] is False


def test_stale_snapshot_is_never_a_reroute_option(monkeypatch):
    from fulfilment_specialist.tools import inventory
    monkeypatch.setattr(inventory, "query_rows", rows(
        {"warehouse_id": "WH-DEL-01", "on_hand": 65, "reserved": 10, "available": 55, "snapshot_at": ago(minutes=12)},
        {"warehouse_id": "WH-HYD-01", "on_hand": 99, "reserved": 0, "available": 99, "snapshot_at": ago(days=2)}))
    options = asyncio.run(inventory.find_stock_elsewhere("SKU-74512", 40, "WH-BLR-01"))["data"]["options"]
    assert [o["warehouse_id"] for o in options] == ["WH-DEL-01"]


# ----------------------------------------------------------------------------- input rules and fixes

def test_positive_int_accepts_what_json_sends_and_nothing_else():
    from common.inputs import positive_int
    assert positive_int(40) == positive_int(40.0) == positive_int("40") == 40
    for bad in (0, -3, 2.5, "forty", None, True):
        assert positive_int(bad) is None
    assert positive_int(999, maximum=60) == 60


def test_quantity_as_float_is_accepted(monkeypatch):
    from fulfilment_specialist.tools import inventory
    monkeypatch.setattr(inventory, "query_rows", rows(_inv(7, 0, 7, 10)))
    data = asyncio.run(inventory.check_inventory("wh-blr-01", "sku-20417", 40.0))["data"]
    assert data["required_quantity"] == 40 and data["shortfall_reason"] == "true_shortage"
    bad = asyncio.run(inventory.check_inventory("WH-BLR-01", "SKU-20417", 2.5))
    assert bad["error_type"] == "invalid_argument"


def test_delivered_parcel_is_never_silent(monkeypatch):
    from orchestrator.tools import events
    base = {"carrier": "Delhivery", "tracking_number": "DLV1", "exception_code": None, "location": "x",
            "description": "d"}
    monkeypatch.setattr(events, "query_rows", rows(
        {**base, "event_id": "CE-1", "event_code": "PICKED_UP", "event_at": ago(hours=120), "received_at": ago(hours=120)},
        {**base, "event_id": "CE-2", "event_code": "DELIVERED", "event_at": ago(hours=73), "received_at": ago(hours=73)}))
    assert events.get_carrier_events("ORD-78401")["data"]["silent_over_hours"] is None
    monkeypatch.setattr(events, "query_rows", rows(                                   # S10: silent for 96 h
        {**base, "event_id": "CE-1", "event_code": "IN_TRANSIT", "event_at": ago(hours=96), "received_at": ago(hours=96)}))
    assert events.get_carrier_events("ORD-78468")["data"]["silent_over_hours"] == 48


def test_payment_holds_are_not_counted_as_change_failures(monkeypatch):
    from orchestrator.tools import events
    change = {"change_id": "CHG-2311", "changed_at": ago(hours=20), "scope": "WH-BOM-01", "description": "",
              "changed_by": "x"}
    order_rows = [{"order_id": "ORD-1", "status": "SHIPPED", "status_reason_code": None, "placed_at": ago(hours=30)},
                  {"order_id": "ORD-2", "status": "ON_HOLD", "status_reason_code": "PAY-H201", "placed_at": ago(hours=10)},
                  {"order_id": "ORD-3", "status": "ON_HOLD", "status_reason_code": "PAY-H201", "placed_at": ago(hours=5)}]
    order_rows = [dict(o, extracted_at=ago(minutes=5)) for o in order_rows]
    answers = iter([[change], order_rows])
    monkeypatch.setattr(events, "query_rows", lambda *a, **k: next(answers))
    monkeypatch.setattr(events, "change_runbook", lambda: ({"status": "ok", "results": []}, None))
    data = events.compare_before_after_change("CHG-2311")["data"]
    assert data["after"]["failed_count"] == 0 and data["pattern"] == "insufficient_before_group"
