"""The specialist's reply contract: what crosses the A2A boundary.

The orchestrator never imports this file (the boundary would not be real). It
reads the same fields from the JSON reply and checks them itself; the Agent
Card description names the contract. ADK validates the reply against this
model before it leaves the specialist (output_schema).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Verdict = Literal["yes", "no", "unknown", "not_applicable"]
Reason = Literal["enough_stock", "true_shortage", "reserved_stock", "stale_inventory", "no_inventory_record",
                 "order_not_found", "already_shipped", "data_unavailable"]


class Reservation(BaseModel):
    order_id: str
    quantity: int
    status: str


class Alternative(BaseModel):
    warehouse_id: str
    available: int


class FulfilmentAnswer(BaseModel):
    order_id: str
    verdict: Verdict = Field(description="Can the ASSIGNED warehouse fulfil the order now?")
    reason: Reason
    warehouse_id: Optional[str] = None
    sku: Optional[str] = None
    ordered: Optional[int] = None
    on_hand: Optional[int] = None
    reserved: Optional[int] = None
    available: Optional[int] = None
    inventory_freshness: Optional[Literal["fresh", "stale"]] = None
    inventory_snapshot_at: Optional[str] = Field(default=None, description="source_time of the inventory read")
    inventory_read_at: Optional[str] = Field(default=None, description="read_at of the inventory read")
    reservations: list[Reservation] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)
    evidence_ids: list[str] = Field(description="evidence_id of every tool result used, copied exactly")
    explanation: str = Field(description="Two or three sentences, facts only, no advice to move stock")
    check_next: list[str] = Field(default_factory=list)
