"""Deterministic read-only enterprise evidence adapters."""

from __future__ import annotations
import json
from pathlib import Path
from app.contracts import Action

DATA = Path(__file__).resolve().parents[1] / "data"

def _load(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))

def execute(action: Action, order_id: str) -> tuple[str, str, dict, str | None]:
    """Return status, source system, payload, source timestamp."""
    mapping = {
        Action.GET_ORDER: ("orders", "order-service"),
        Action.CHECK_INVENTORY: ("inventory", "inventory-service"),
        Action.CHECK_PAYMENT_HOLD: ("payments", "payment-service"),
        Action.CHECK_WAREHOUSE: ("warehouses", "warehouse-service"),
        Action.GET_CARRIER_STATUS: ("carriers", "carrier-service"),
        Action.GET_RECENT_CHANGES: ("changes", "change-service"),
    }
    if action == Action.SEARCH_OPERATIONS_KNOWLEDGE:
        payload = _load("knowledge").get("default", [])
        return "SUCCESS", "operations-kb", {"matches": payload}, None

    if action not in mapping:
        return "INVALID_RESPONSE", "runtime", {}, None

    file_name, source = mapping[action]
    payload = _load(file_name).get(order_id)
    if payload is None:
        return "NOT_FOUND", source, {}, None

    timestamp = (
        payload.get("updated_at")
        or payload.get("last_updated")
        or payload.get("snapshot_time")
        or payload.get("last_event")
    )
    return "SUCCESS", source, payload, timestamp
