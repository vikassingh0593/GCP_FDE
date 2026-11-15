"""Deterministic enterprise evidence tools for the Day-2 semantic orchestrator."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[2] / "data"

def _load(name: str) -> dict[str, Any]:
    return json.loads((DATA / name).read_text())

def get_ticket(ticket_id: str) -> dict[str, Any]:
    """Return the support ticket and symptoms."""
    return _load("tickets.json").get(ticket_id, {"error": "TICKET_NOT_FOUND"})

def get_product_telemetry(ticket_id: str) -> dict[str, Any]:
    """Return telemetry relevant to the ticket."""
    return _load("telemetry.json").get(ticket_id, {"error": "TELEMETRY_NOT_FOUND"})

def get_recent_changes(ticket_id: str) -> dict[str, Any]:
    """Return recent changes that may explain the symptoms."""
    return {"changes": _load("changes.json").get(ticket_id, [])}

def search_support_knowledge(symptom: str) -> dict[str, Any]:
    """Search known support patterns by normalized symptom."""
    return {"matches": _load("knowledge.json").get(symptom, [])}

def validate_identity_binding(ticket_id: str) -> dict[str, Any]:
    """Validate the workspace identity binding for the ticket."""
    return _load("identity.json").get(ticket_id, {"error": "IDENTITY_DATA_NOT_FOUND"})

TOOL_REGISTRY = {
    "GET_TICKET": get_ticket,
    "GET_TELEMETRY": get_product_telemetry,
    "GET_RECENT_CHANGES": get_recent_changes,
    "SEARCH_KNOWLEDGE": search_support_knowledge,
    "VALIDATE_IDENTITY_BINDING": validate_identity_binding,
}
