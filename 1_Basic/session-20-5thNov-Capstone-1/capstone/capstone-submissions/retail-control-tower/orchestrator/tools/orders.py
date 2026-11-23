"""Order lookup (session 13 get_incident pattern, on BigQuery).

Returns only the fields the investigation needs. Customer name, phone and
address exist in the orders table but never leave this tool (Gate 1).
payment_status is returned because a payment hold can be the cause, and it is
masked in every log.

Time arithmetic is done here, not by the model: hours since placed, hours past
the promise, hours since the last status change.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from common import config, results
from common.clients import query_rows
from common.freshness import hours_ago
from common.inputs import ORDER_ID, clean_id

SHIPPED = ("SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED")


def get_order(order_id: str, tool_context: ToolContext) -> dict:
    """Authoritative record of one order: status, reason code, SKU, quantity, assigned warehouse, carrier, dates.

    Use first in every order investigation. It also sets this order as the
    session's current order. Read-only.
    """
    order_id = clean_id(order_id)
    if not ORDER_ID.match(order_id):
        return results.error("bigquery:orders", "invalid_argument", "order_id must look like ORD-12345")

    from google.cloud import bigquery
    rows = query_rows(f"""
        SELECT order_id, order_type, sku, quantity, warehouse_id, status, status_reason_code, payment_status,
               carrier, tracking_number, placed_at, promised_delivery_at, last_updated_at, extracted_at
        FROM `{config.table_id(config.OPERATIONAL_TABLES['orders'])}`
        WHERE order_id = @order_id""",
        [bigquery.ScalarQueryParameter("order_id", "STRING", order_id)], "get_order")
    if not rows:
        return results.not_found("ORD", order_id, "bigquery:orders",
                                 f"Order {order_id} does not exist in the order system. Do not guess its status.")

    r = rows[0]
    now = results.now_utc()
    past_promise = hours_ago(r["promised_delivery_at"], now)
    data = {
        "order_id": r["order_id"], "order_type": r["order_type"], "sku": r["sku"], "quantity": r["quantity"],
        "warehouse_id": r["warehouse_id"], "status": r["status"], "status_reason_code": r["status_reason_code"],
        "payment_status": r["payment_status"], "carrier": r["carrier"], "tracking_number": r["tracking_number"],
        "shipped": r["status"] in SHIPPED,
        "placed_hours_ago": hours_ago(r["placed_at"], now),
        "promised_in_hours": -past_promise if past_promise is not None else None,
        "overdue": past_promise is not None and past_promise > 0 and r["status"] != "DELIVERED",
        "hours_overdue": past_promise if past_promise and past_promise > 0 else 0,
        "hours_since_status_change": hours_ago(r["last_updated_at"], now),
    }
    # Session state: the current case (Gate 8). Survives the next turn, not a new session.
    tool_context.state["current_order_id"] = r["order_id"]
    tool_context.state["current_warehouse_id"] = r["warehouse_id"]
    return results.ok("ORD", order_id, "bigquery:orders", data, source_time=r["extracted_at"],
                      max_age_minutes=config.ORDER_MAX_AGE_MINUTES, now=now)
