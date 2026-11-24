"""The Fulfilment Specialist's tools: the only data it can read (session 19 tools.py, on BigQuery).

Same shape as session 19 (get the order line, check inventory, compare), with
what production needs:
- read live from BigQuery, never from a cache: inventory decides the answer;
- every result carries its source time and freshness, decided here in code;
- a stale snapshot gives can_fulfil = None (unknown), never a yes or no;
- "no inventory row" is reported as no record, never as zero stock;
- the order line has fulfilment fields only: no customer details, no payment.

The tools are async and run the BigQuery call in a worker thread
(asyncio.to_thread). A blocking call on the A2A server's event loop would
stall every other request to this service, including its Agent Card. (The
orchestrator gets the same effect from RunConfig.tool_thread_pool_config; here
the RunConfig is built by ADK's A2A request converter, so the tools do it.)

Read-only. Nothing here reserves, releases or moves stock.
"""

from __future__ import annotations

import asyncio
from typing import Any

from common import config, results
from common.clients import query_rows
from common.freshness import freshness, hours_ago
from common.inputs import ORDER_ID, SKU, WAREHOUSE_ID, clean_id, positive_int

SHIPPED = ("SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED")
HOLDING_STOCK = ("ALLOCATED", "PICKING", "PACKED")   # statuses that hold a reservation


def _param(name: str, value: Any, kind: str = "STRING"):
    from google.cloud import bigquery
    return bigquery.ScalarQueryParameter(name, kind, value)


async def _rows(sql: str, params: list, what: str) -> list[dict]:
    return await asyncio.to_thread(query_rows, sql, params, what)


async def get_order_line(order_id: str) -> dict:
    """Fulfilment fields of one order: SKU, quantity, assigned warehouse, status.

    Use first, for every fulfilment check. Read-only.
    """
    order_id = clean_id(order_id)
    if not ORDER_ID.match(order_id):
        return results.error("bigquery:orders", "invalid_argument", "order_id must look like ORD-12345")
    rows = await _rows(f"""
        SELECT order_id, order_type, sku, quantity, warehouse_id, status, status_reason_code,
               placed_at, promised_delivery_at, extracted_at
        FROM `{config.table_id(config.OPERATIONAL_TABLES['orders'])}`
        WHERE order_id = @order_id
        ORDER BY extracted_at DESC LIMIT 1""", [_param("order_id", order_id)], "get_order_line")
    if not rows:
        return results.not_found("OL", order_id, "bigquery:orders", f"Order {order_id} does not exist.")
    r = rows[0]
    now = results.now_utc()
    data = {
        "order_id": r["order_id"], "order_type": r["order_type"], "sku": r["sku"], "quantity": r["quantity"],
        "warehouse_id": r["warehouse_id"], "status": r["status"], "status_reason_code": r["status_reason_code"],
        "already_shipped": r["status"] in SHIPPED,
        "placed_hours_ago": hours_ago(r["placed_at"], now),
        "hours_past_promise": hours_ago(r["promised_delivery_at"], now),
    }
    return results.ok("OL", order_id, "bigquery:orders", data, source_time=r["extracted_at"],
                      max_age_minutes=config.ORDER_MAX_AGE_MINUTES, now=now)


async def check_inventory(warehouse_id: str, sku: str, required_quantity: int) -> dict:
    """On hand, reserved and available stock for one warehouse and SKU, and whether it covers the quantity.

    can_fulfil is True/False only when the snapshot is fresh; a stale snapshot
    gives None (unknown). shortfall_reason says why a fresh snapshot falls short:
    true_shortage (on hand below the quantity) or reserved_stock (enough on hand,
    but held for other orders). Read-only.
    """
    warehouse_id, sku = clean_id(warehouse_id), clean_id(sku)
    if not WAREHOUSE_ID.match(warehouse_id) or not SKU.match(sku):
        return results.error("bigquery:inventory", "invalid_argument",
                             "warehouse_id must look like WH-BLR-01 and sku like SKU-12345")
    required = positive_int(required_quantity)
    if required is None:
        return results.error("bigquery:inventory", "invalid_argument", "required_quantity must be a positive whole number")

    key = f"{warehouse_id}/{sku}"
    rows = await _rows(f"""
        SELECT warehouse_id, sku, on_hand, reserved, available, snapshot_at
        FROM `{config.table_id(config.OPERATIONAL_TABLES['inventory'])}`
        WHERE warehouse_id = @warehouse_id AND sku = @sku
        ORDER BY snapshot_at DESC LIMIT 1""",
        [_param("warehouse_id", warehouse_id), _param("sku", sku)], "check_inventory")
    if not rows:
        return results.not_found("INV", key, "bigquery:inventory",
                                 f"No inventory record for {sku} at {warehouse_id}. This is not the same as "
                                 "zero stock: the warehouse may not stock this SKU, or the record is missing.")
    r = rows[0]
    now = results.now_utc()
    fresh = freshness(r["snapshot_at"], config.INVENTORY_MAX_AGE_MINUTES, now) == "fresh"
    if not fresh:
        can_fulfil, shortfall = None, None
    elif r["available"] >= required:
        can_fulfil, shortfall = True, None
    else:
        can_fulfil = False
        shortfall = "true_shortage" if r["on_hand"] < required else "reserved_stock"
    data = {
        "warehouse_id": warehouse_id, "sku": sku, "required_quantity": required,
        "on_hand": r["on_hand"], "reserved": r["reserved"], "available": r["available"],
        "snapshot_hours_ago": hours_ago(r["snapshot_at"], now),
        "can_fulfil": can_fulfil, "shortfall_reason": shortfall,
        "note": None if fresh else (f"Snapshot is stale (older than {config.INVENTORY_MAX_AGE_MINUTES} minutes): "
                                    "these numbers are not current evidence. Fulfilment is unknown until the "
                                    "snapshot is refreshed."),
    }
    return results.ok("INV", key, "bigquery:inventory", data, source_time=r["snapshot_at"],
                      max_age_minutes=config.INVENTORY_MAX_AGE_MINUTES, now=now)


async def find_reservations(warehouse_id: str, sku: str, exclude_order_id: str = "") -> dict:
    """Orders that currently hold stock of this SKU at this warehouse (allocated, picking or packed).

    Use when check_inventory says reserved_stock, to name the orders holding it.
    Read-only: releasing a reservation is a human decision, never done here.
    """
    warehouse_id, sku = clean_id(warehouse_id), clean_id(sku)
    if not WAREHOUSE_ID.match(warehouse_id) or not SKU.match(sku):
        return results.error("bigquery:orders", "invalid_argument",
                             "warehouse_id must look like WH-BLR-01 and sku like SKU-12345")
    from google.cloud import bigquery
    rows = await _rows(f"""
        SELECT order_id, order_type, quantity, status, placed_at, promised_delivery_at, extracted_at
        FROM `{config.table_id(config.OPERATIONAL_TABLES['orders'])}`
        WHERE warehouse_id = @warehouse_id AND sku = @sku AND status IN UNNEST(@holding)
          AND order_id != @exclude
        ORDER BY quantity DESC, order_id""",
        [_param("warehouse_id", warehouse_id), _param("sku", sku), _param("exclude", clean_id(exclude_order_id)),
         bigquery.ArrayQueryParameter("holding", "STRING", list(HOLDING_STOCK))], "find_reservations")
    now = results.now_utc()
    holders = []
    for r in rows:
        past_promise = hours_ago(r["promised_delivery_at"], now)
        holders.append({"order_id": r["order_id"], "order_type": r["order_type"], "quantity": r["quantity"],
                        "status": r["status"], "placed_hours_ago": hours_ago(r["placed_at"], now),
                        "promise_in_hours": -past_promise if past_promise is not None else None})
    # The OLDEST row decides freshness: one stale row makes the reservation list stale.
    source_time = min((r["extracted_at"] for r in rows), default=None)
    return results.ok("RES", f"{warehouse_id}/{sku}", "bigquery:orders",
                      {"warehouse_id": warehouse_id, "sku": sku, "holding_orders": holders,
                       "total_held": sum(h["quantity"] for h in holders)},
                      source_time=source_time, max_age_minutes=config.ORDER_MAX_AGE_MINUTES if rows else None,
                      now=now)


async def find_stock_elsewhere(sku: str, required_quantity: int, exclude_warehouse_id: str = "") -> dict:
    """Other warehouses with a fresh snapshot and enough available stock of this SKU (re-route options).

    An option only: a re-route needs Fulfilment duty manager approval. Read-only.
    """
    sku = clean_id(sku)
    required = positive_int(required_quantity)
    if not SKU.match(sku) or required is None:
        return results.error("bigquery:inventory", "invalid_argument",
                             "sku must look like SKU-12345 and required_quantity be a positive whole number")
    rows = await _rows(f"""
        SELECT warehouse_id, on_hand, reserved, available, snapshot_at
        FROM `{config.table_id(config.OPERATIONAL_TABLES['inventory'])}`
        WHERE sku = @sku AND warehouse_id != @exclude
        ORDER BY available DESC, warehouse_id""",
        [_param("sku", sku), _param("exclude", clean_id(exclude_warehouse_id))], "find_stock_elsewhere")
    now = results.now_utc()
    options = []
    for r in rows:
        if freshness(r["snapshot_at"], config.INVENTORY_MAX_AGE_MINUTES, now) != "fresh":
            continue                                   # a stale snapshot is not an option
        if r["available"] >= required:
            options.append({"warehouse_id": r["warehouse_id"], "available": r["available"],
                            "snapshot_hours_ago": hours_ago(r["snapshot_at"], now),
                            "evidence_id": results.evidence_id("INV", f"{r['warehouse_id']}/{sku}", r["snapshot_at"])})
    return results.ok("ALT", sku, "bigquery:inventory",
                      {"sku": sku, "required_quantity": required, "options": options,
                       "note": "Re-route needs Fulfilment duty manager approval."},
                      source_time=max((r["snapshot_at"] for r in rows), default=None),
                      max_age_minutes=config.INVENTORY_MAX_AGE_MINUTES if rows else None, now=now)


TOOLS = [get_order_line, check_inventory, find_reservations, find_stock_elsewhere]
