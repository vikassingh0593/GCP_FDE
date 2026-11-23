"""Escalation to an analyst queue: the only write in the system, and it needs a human yes (Gate 11).

The tool is registered with require_confirmation=True. When the model calls
it, ADK pauses the run and asks the client for confirmation (an
adk_request_confirmation event). The web app shows the draft; nothing is saved
until the analyst confirms. A declined draft is never written.

Idempotent: the escalation ID comes from the session and the order, so a double
click or a retried request finds the existing row instead of writing a second.
Append-only table; it is not truncated by the daily data reload.
"""

from __future__ import annotations

import hashlib

from google.adk.tools import FunctionTool, ToolContext

from common import config, results
from common.clients import bigquery_client, query_rows, with_retry
from common.inputs import EVIDENCE_ID, ORDER_ID, clean_id
OWNERS = ("Fulfilment duty manager", "Inventory Control", "Logistics Operations", "Payments Risk",
          "Warehouse Operations", "Change owner", "Order system team")

ESCALATIONS_SCHEMA = [
    ("escalation_id", "STRING", "REQUIRED"), ("created_at", "TIMESTAMP", "REQUIRED"),
    ("order_id", "STRING", "REQUIRED"), ("owner_team", "STRING", "REQUIRED"), ("summary", "STRING", "REQUIRED"),
    ("check_next", "STRING", "REPEATED"), ("evidence_ids", "STRING", "REPEATED"),
    ("session_id", "STRING", "NULLABLE"), ("analyst", "STRING", "NULLABLE"),
    ("correlation_id", "STRING", "NULLABLE"), ("status", "STRING", "REQUIRED"),
]


def _ensure_table():
    from google.cloud import bigquery
    table = bigquery.Table(config.table_id(config.BQ_ESCALATIONS_TABLE),
                           schema=[bigquery.SchemaField(n, t, mode=m) for n, t, m in ESCALATIONS_SCHEMA])
    table.description = "Escalations confirmed by an analyst (append-only; never truncated by load_data)."
    return bigquery_client().create_table(table, exists_ok=True)


def escalate_case(order_id: str, owner_team: str, summary: str, check_next: list[str],
                  evidence_ids: list[str], tool_context: ToolContext) -> dict:
    """Save an escalation for an analyst queue, after the analyst confirms it.

    Use when the evidence conflicts or the investigation can't conclude and a
    named team must act. owner_team must be one of: Fulfilment duty manager,
    Inventory Control, Logistics Operations, Payments Risk, Warehouse Operations,
    Change owner, Order system team. summary = what is known, in two sentences;
    check_next = what that team should check; evidence_ids = the IDs the summary
    rests on. The analyst sees this draft and confirms or declines it.
    """
    order_id = clean_id(order_id)
    if not ORDER_ID.match(order_id):
        return results.error("bigquery:escalations", "invalid_argument", "order_id must look like ORD-12345")
    if owner_team not in OWNERS:
        return results.error("bigquery:escalations", "invalid_argument", f"owner_team must be one of {OWNERS}")
    if not (summary or "").strip() or not check_next:
        return results.error("bigquery:escalations", "invalid_argument", "summary and check_next are required")

    session_id = tool_context.session.id if getattr(tool_context, "session", None) else ""
    escalation_id = "ESC-" + hashlib.sha256(f"{session_id}|{order_id}".encode()).hexdigest()[:10].upper()
    metadata = dict(getattr(tool_context.run_config, "custom_metadata", None) or {})

    from google.cloud import bigquery
    _ensure_table()
    existing = query_rows(f"SELECT escalation_id FROM `{config.table_id(config.BQ_ESCALATIONS_TABLE)}` "
                          "WHERE escalation_id = @id", [bigquery.ScalarQueryParameter("id", "STRING", escalation_id)],
                          "escalation_lookup")
    if existing:
        return results.ok("ESC", escalation_id, "bigquery:escalations",
                          {"escalation_id": escalation_id, "saved": False,
                           "note": "Already escalated in this session; no duplicate written."})

    now = results.now_utc()
    row = {"escalation_id": escalation_id, "created_at": results.iso(now), "order_id": order_id,
           "owner_team": owner_team, "summary": summary.strip()[:2000], "check_next": [c[:300] for c in check_next][:10],
           # Only well-formed evidence IDs are stored: the row must point at real trace evidence.
           "evidence_ids": [e for e in (evidence_ids or []) if isinstance(e, str) and EVIDENCE_ID.fullmatch(e)][:30],
           "session_id": session_id,
           "analyst": tool_context.user_id, "correlation_id": metadata.get("correlation_id"),
           "status": "open"}
    # A load job, not a streaming insert: a freshly created table can reject streaming rows for a
    # while, and load jobs are free. The lookup above makes a repeat call safe.
    job = with_retry(lambda: bigquery_client().load_table_from_json(
        [row], config.table_id(config.BQ_ESCALATIONS_TABLE), job_config=bigquery.LoadJobConfig(
            schema=[bigquery.SchemaField(n, t, mode=m) for n, t, m in ESCALATIONS_SCHEMA],
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND)), "escalation_insert")
    job.result(timeout=30)
    return results.ok("ESC", escalation_id, "bigquery:escalations",
                      {"escalation_id": escalation_id, "saved": True, "owner_team": owner_team}, now=now)


escalate_case_tool = FunctionTool(escalate_case, require_confirmation=True)
