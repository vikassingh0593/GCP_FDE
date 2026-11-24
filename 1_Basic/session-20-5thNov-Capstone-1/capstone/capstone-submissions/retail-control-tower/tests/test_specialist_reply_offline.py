"""fulfilment_specialist/fulfilment_agent/reply.py: the reply's verdict and numbers come from code."""

from __future__ import annotations

from common import results
from fakes import ago
from fulfilment_specialist.fulfilment_agent.reply import build_reply

LINE = results.ok("OL", "ORD-78421", "bigquery:orders", {
    "order_id": "ORD-78421", "order_type": "B2B", "sku": "SKU-74512", "quantity": 40, "warehouse_id": "WH-BLR-01",
    "status": "ALLOCATION_PENDING", "status_reason_code": "ALLOC-E101", "already_shipped": False},
    source_time=ago(minutes=5), max_age_minutes=300)


def inventory(available, on_hand, minutes_old=10, qty=40, sku="SKU-74512", can=None, shortfall=None):
    fresh = minutes_old <= 300
    return results.ok("INV", f"WH-BLR-01/{sku}", "bigquery:inventory", {
        "warehouse_id": "WH-BLR-01", "sku": sku, "required_quantity": qty, "on_hand": on_hand,
        "reserved": on_hand - available, "available": available,
        "can_fulfil": (available >= qty) if fresh and can is None else can,
        "shortfall_reason": shortfall}, source_time=ago(minutes=minutes_old), max_age_minutes=300)


def test_shortage_is_no_with_numbers_and_ids_from_the_results():
    inv = inventory(7, 7, shortfall="true_shortage")
    reply, notes = build_reply("ORD-78421", {"get_order_line": LINE, "check_inventory": inv})
    assert (reply["verdict"], reply["reason"], reply["available"], reply["ordered"]) == ("no", "true_shortage", 7, 40)
    assert reply["evidence_ids"] == [LINE["evidence_id"], inv["evidence_id"]]
    assert reply["inventory_freshness"] == "fresh" and reply["inventory_snapshot_at"] == inv["source_time"]


def test_stale_snapshot_is_unknown_never_yes():
    inv = inventory(70, 80, minutes_old=2 * 24 * 60, qty=40, can=None)
    reply, notes = build_reply("ORD-78421", {"get_order_line": LINE, "check_inventory": inv})
    assert (reply["verdict"], reply["reason"]) == ("unknown", "stale_inventory")
    assert any("refresh the WH-BLR-01 / SKU-74512" in n for n in notes)


def test_inventory_checked_against_the_wrong_quantity_or_sku_is_unknown():
    for inv in (inventory(30, 30, qty=4), inventory(30, 30, sku="SKU-99999")):
        reply, _ = build_reply("ORD-78421", {"get_order_line": LINE, "check_inventory": inv})
        assert (reply["verdict"], reply["reason"]) == ("unknown", "data_unavailable")


def test_missing_or_failed_lookups_are_unknown():
    assert build_reply("ORD-78421", {})[0]["reason"] == "data_unavailable"
    assert build_reply("ORD-78421", {"get_order_line": LINE})[0]["reason"] == "data_unavailable"
    gone = results.not_found("INV", "WH-BLR-01/SKU-74512", "bigquery:inventory", "no record")
    assert build_reply("ORD-78421", {"get_order_line": LINE, "check_inventory": gone})[0]["reason"] == \
        "no_inventory_record"
