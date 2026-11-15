from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_DATA_DIR=Path(__file__).resolve().parents[1]/"data"

def _load_json(filename: str) -> dict[str, Any]:
    """Load one local dataset representing an enterprise source."""
    return json.loads((_DATA_DIR/filename).read_text(encoding="utf-8"))


def get_order(order_id: str) -> dict[str, Any]:
    """Return authoritative order details or a safe NOT_FOUND result."""
    order=_load_json("orders.json").get(order_id)
    if order is None:
        return {"status":"NOT_FOUND","order_id":order_id}
    return {"status":"SUCCESS","order":order}

def check_inventory(warehouse_id: str, sku: str, required_quantity: int) -> dict[str, Any]:
    """Return inventory evidence and whether the quantity can be fulfilled."""
    record=_load_json("inventory.json").get(f"{warehouse_id}:{sku}")
    if record is None:
        return {"status":"NOT_FOUND","warehouse_id":warehouse_id,"sku":sku}
    available=int(record["available_quantity"])
    return {
        "status":"SUCCESS",
        "warehouse_id":warehouse_id,
        "sku":sku,
        "required_quantity":required_quantity,
        "available_quantity":available,
        "can_fulfil":available >= required_quantity,
    }
