"""Deterministic business capabilities exposed by the MCP server.

Architecture role:
    Enterprise data -> Python business function -> MCP server -> MCP client

These functions intentionally contain no Gemini or ADK code. They represent the
enterprise capabilities that another team/service could own in production.

Test directly:
    pytest -q
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_json(filename: str) -> dict[str, Any]:
    """Load one local JSON file used to simulate an enterprise system."""
    path = DATA_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def get_order(order_id: str) -> dict[str, Any]:
    """Return authoritative details for one order.

    Args:
        order_id: Enterprise order identifier, for example ``ORD-1001``.

    Returns:
        A structured SUCCESS or NOT_FOUND result.
    """
    order = _load_json("orders.json").get(order_id)

    if order is None:
        return {
            "status": "NOT_FOUND",
            "order_id": order_id,
        }

    return {
        "status": "SUCCESS",
        "order": order,
    }


def check_inventory(
    warehouse_id: str,
    sku: str,
    required_quantity: int,
) -> dict[str, Any]:
    """Check whether one warehouse can fulfil the requested SKU quantity.

    The tool returns evidence; it does not ask a model to infer availability.
    """
    inventory_key = f"{warehouse_id}:{sku}"
    record = _load_json("inventory.json").get(inventory_key)

    if record is None:
        return {
            "status": "NOT_FOUND",
            "warehouse_id": warehouse_id,
            "sku": sku,
        }

    available_quantity = int(record["available_quantity"])

    return {
        "status": "SUCCESS",
        "warehouse_id": warehouse_id,
        "sku": sku,
        "required_quantity": required_quantity,
        "available_quantity": available_quantity,
        "can_fulfil": available_quantity >= required_quantity,
        "inventory_status": record["inventory_status"],
    }


def get_customer(customer_id: str) -> dict[str, Any]:
    """Return basic customer information for an order investigation."""
    customer = _load_json("customers.json").get(customer_id)

    if customer is None:
        return {
            "status": "NOT_FOUND",
            "customer_id": customer_id,
        }

    return {
        "status": "SUCCESS",
        "customer": customer,
    }
