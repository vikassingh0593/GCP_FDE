"""Knowledge search as a tool, not an agent: it retrieves, it doesn't decide (decision matrix: Agents = 2)."""

from __future__ import annotations

from orchestrator.retrieval.search import search


def search_knowledge(query: str, doc_type: str = "", exception_type: str = "", warehouse_id: str = "") -> dict:
    """Search current runbooks (procedures: how to check, who decides) and postmortems (past incidents).

    Put exact codes in the query when you have them (ALLOC-E107, WX-HOLD, PAY-H201,
    SYSTEM_DOWN): exact codes are matched word for word. Optional filters:
    doc_type = runbook | postmortem; exception_type = inventory_shortage | allocation |
    carrier_delay | payment_hold | warehouse_disruption | recent_change; warehouse_id
    narrows postmortems to one warehouse.

    Postmortem results are historical hints: never proof of today's cause.
    status no_evidence means the documents don't cover the question: say so.
    """
    return search(query, doc_type=doc_type or None, exception_type=exception_type or None,
                  warehouse_id=(warehouse_id or "").upper() or None)
