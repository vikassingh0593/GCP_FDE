"""The specialist's reply is decided by code, from its own tool results (review blocker #1).

The model chooses which lookups to make and writes the explanation. It does
NOT decide the verdict, the reason, the stock numbers, the snapshot time or the
evidence IDs: an LLM copying numbers can drop one, round one, or (worst)
answer "yes" from a stale snapshot. So:

1. after_tool keeps every tool result of this request (temp: state, gone after
   the request);
2. before_tool, when the model calls set_model_response to reply, overwrites
   every decision field with build_reply(...) computed from those results;
   only `explanation` and `check_next` stay the model's (code adds its own
   check_next items when the data demands them).

If the lookups don't fit together (inventory read for another warehouse, SKU
or quantity than the order line) the verdict is unknown / data_unavailable,
never a guess. Evidence IDs come only from results the specialist really got,
so nothing invented can cross A2A.
"""

from __future__ import annotations

from typing import Any

RESULTS_KEY = "temp:fulfilment_results"      # tool name -> latest result, this request only
DECISION_FIELDS = ("order_id", "verdict", "reason", "warehouse_id", "sku", "ordered", "on_hand", "reserved",
                   "available", "inventory_freshness", "inventory_snapshot_at", "inventory_read_at",
                   "reservations", "alternatives", "evidence_ids")


def _ok(result: dict | None) -> bool:
    return isinstance(result, dict) and result.get("status") == "ok"


def build_reply(order_id: str, found: dict[str, dict]) -> tuple[dict, list[str]]:
    """(decision fields, check_next items added by code) from the tool results of this request."""
    line, inv = found.get("get_order_line"), found.get("check_inventory")
    res, alt = found.get("find_reservations"), found.get("find_stock_elsewhere")
    reply: dict[str, Any] = {"order_id": order_id, "warehouse_id": None, "sku": None, "ordered": None,
                             "on_hand": None, "reserved": None, "available": None, "inventory_freshness": None,
                             "inventory_snapshot_at": None, "inventory_read_at": None, "reservations": [],
                             "alternatives": [], "evidence_ids": []}
    notes: list[str] = []

    def done(verdict: str, reason: str) -> tuple[dict, list[str]]:
        reply["verdict"], reply["reason"] = verdict, reason
        return reply, notes

    if not isinstance(line, dict) or line.get("status") == "error":
        notes.append("run the fulfilment check again: the order line could not be read")
        return done("unknown", "data_unavailable")
    if line.get("evidence_id"):
        reply["evidence_ids"].append(line["evidence_id"])
    if line.get("status") == "not_found":
        return done("unknown", "order_not_found")
    o = line["data"]
    if o["order_id"] != order_id:
        notes.append("the order line read was for a different order")
        return done("unknown", "data_unavailable")
    reply.update(warehouse_id=o["warehouse_id"], sku=o["sku"], ordered=o["quantity"])
    if o.get("already_shipped"):
        return done("not_applicable", "already_shipped")

    if not isinstance(inv, dict) or inv.get("status") == "error":
        notes.append(f"run the inventory check for {o['warehouse_id']} / {o['sku']} again")
        return done("unknown", "data_unavailable")
    if inv.get("evidence_id"):
        reply["evidence_ids"].append(inv["evidence_id"])
    if inv.get("status") == "not_found":
        notes.append(f"ask Inventory Control whether {o['warehouse_id']} stocks {o['sku']} at all")
        return done("unknown", "no_inventory_record")
    d = inv["data"]
    if (d["warehouse_id"], d["sku"], d["required_quantity"]) != (o["warehouse_id"], o["sku"], o["quantity"]):
        notes.append("the inventory check did not match the order line; run the fulfilment check again")
        return done("unknown", "data_unavailable")
    reply.update(on_hand=d["on_hand"], reserved=d["reserved"], available=d["available"],
                 inventory_freshness=inv.get("freshness"), inventory_snapshot_at=inv.get("source_time"),
                 inventory_read_at=inv.get("read_at"))

    if _ok(res) and res["data"]["warehouse_id"] == o["warehouse_id"] and res["data"]["sku"] == o["sku"]:
        reply["reservations"] = [{"order_id": h["order_id"], "quantity": h["quantity"], "status": h["status"]}
                                 for h in res["data"]["holding_orders"]]
        reply["evidence_ids"].append(res["evidence_id"])
    if _ok(alt) and alt["data"]["sku"] == o["sku"] and alt["data"]["required_quantity"] == o["quantity"]:
        reply["alternatives"] = [{"warehouse_id": a["warehouse_id"], "available": a["available"]}
                                 for a in alt["data"]["options"] if a["warehouse_id"] != o["warehouse_id"]]
        reply["evidence_ids"].append(alt["evidence_id"])

    if inv.get("freshness") != "fresh" or d["can_fulfil"] is None:
        notes.append(f"refresh the {o['warehouse_id']} / {o['sku']} inventory snapshot with Inventory Control")
        return done("unknown", "stale_inventory")
    if d["can_fulfil"]:
        return done("yes", "enough_stock")
    return done("no", d["shortfall_reason"])


def remember_result(tool, args: dict, tool_context, tool_response: dict) -> None:
    """after_tool: keep this request's tool results for build_reply (never changes the result)."""
    if tool.name == "set_model_response" or not isinstance(tool_response, dict):
        return None
    found = dict(tool_context.state.get(RESULTS_KEY) or {})
    found[tool.name] = tool_response
    tool_context.state[RESULTS_KEY] = found
    return None


def decide_reply(tool, args: dict, tool_context) -> None:
    """before_tool: when the model replies, the decision fields are replaced by code's."""
    if tool.name != "set_model_response":
        return None
    found = dict(tool_context.state.get(RESULTS_KEY) or {})
    line = found.get("get_order_line")
    order_id = (line or {}).get("data", {}).get("order_id") if _ok(line) else str(args.get("order_id") or "")
    decided, notes = build_reply(order_id, found)
    model_said = {k: args.get(k) for k in ("verdict", "reason", "available")}
    args.update(decided)                                   # same dict the tool runs with
    args["check_next"] = list(dict.fromkeys([*(args.get("check_next") or []), *notes]))
    if any(model_said[k] not in (None, decided[k]) for k in model_said):
        args["explanation"] = (f"[Values set by code from the tool results: verdict {decided['verdict']}, "
                               f"reason {decided['reason']}.] " + str(args.get("explanation") or ""))
    return None
