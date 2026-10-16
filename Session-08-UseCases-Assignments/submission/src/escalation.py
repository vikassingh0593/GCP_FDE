"""Hand-off to a person (Step 7, decision D52): the human in the loop at the risk boundary.

The brief's §11 table marks medical escalation "Approval? Yes": a question the
assistant must not decide (one specific patient, a conflict between valid
sources, or a user asking for a person) goes to Medical Information. Nothing
here uses a model:

  1. an escalation record is appended to BigQuery `escalations` (status OPEN);
     a person works that queue (production: a Pub/Sub hook sends it to email or
     the ticket system, §13);
  2. the user gets a fixed hand-off message with the escalation ID; if the
     record could not be written, the message says so: never claim a hand-off
     that did not happen;
  3. for a patient case with a known country, the NORMAL checked search runs on a
     general version of the question (no patient details, written by the agent)
     and is shown under a fixed header: general reference, not a recommendation.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

from google.cloud import bigquery

import rag_runtime as rt
import replay
from config import BQ_ESCALATIONS_TABLE, OUTPUT_DIR, table_id
from policy import (ESCALATION_REASONS, GENERAL_REFERENCE_HEADER, HANDOFF, HANDOFF_FAILED, HANDOFF_PATIENT,
                    HANDOFF_REQUEST, TOPIC_HINTS)


SCHEMA = [
    bigquery.SchemaField("escalation_id", "STRING", "REQUIRED"),
    bigquery.SchemaField("created_at", "TIMESTAMP", "REQUIRED"),
    bigquery.SchemaField("reason", "STRING", description="patient_specific, user_request or conflict."),
    bigquery.SchemaField("question", "STRING", description="The user's question as asked."),
    bigquery.SchemaField("general_question", "STRING", description="The question without patient details (agent)."),
    bigquery.SchemaField("country", "STRING"),
    bigquery.SchemaField("caller", "STRING", description="Tool or code path that escalated."),
    bigquery.SchemaField("team", "STRING", description="Who must handle it."),
    bigquery.SchemaField("status", "STRING", description="OPEN until a person handles it."),
    bigquery.SchemaField("general_reference_outcome", "STRING", description="Outcome of the general search, if run."),
    bigquery.SchemaField("run_tag", "STRING", description="eval, demo, smoke or record for test traffic (D60)."),
]


def _record(row: dict) -> tuple[bool, str]:
    """Append the escalation; offline it goes to a local file (tests never reach the cloud)."""
    if replay.offline():
        with (OUTPUT_DIR / "escalations_offline.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        return True, "offline"
    try:
        client = rt._bq()
        table = client.create_table(bigquery.Table(table_id(BQ_ESCALATIONS_TABLE), schema=SCHEMA), exists_ok=True)
        missing = [f for f in SCHEMA if f.name not in {s.name for s in table.schema}]
        if missing:  # new columns are added without touching existing rows
            table.schema = list(table.schema) + missing
            client.update_table(table, ["schema"])
        errors = rt.with_retry(lambda: client.insert_rows_json(table_id(BQ_ESCALATIONS_TABLE), [row]), "escalations")
        return (not errors), (str(errors)[:160] if errors else "ok")
    except Exception as exc:
        return False, str(exc)[:160]


def escalate(reason: str, question: str, general_question: str = "", country: str | None = None,
             caller: str = "cli") -> dict:
    """Record the hand-off, then return the fixed message (+ a general reference for a patient case)."""
    reason = reason if reason in ESCALATION_REASONS else "user_request"
    escalation_id = "ESC-" + uuid.uuid4().hex[:8].upper()
    team = HANDOFF["medical"]
    result = {"log_id": uuid.uuid4().hex, "question": question, "mode": "escalate", "country": rt.normalize_country(country),
              "filters": {"reason": reason, "escalation_id": escalation_id}, "candidates": [], "reranked": [],
              "cards": [], "reasons": [reason], "latency_ms": {}, "sources": "", "notes": [],
              "citation_check": "fixed hand-off text (no generation)", "escalation_id": escalation_id}

    # 3 first, so its outcome is part of the record (the search is the normal checked pipeline).
    # The agent is asked to remove patient details, but code makes sure: every token with a digit
    # (an age, "eGFR 35", "4x ULN", "50 mg") is dropped, so the general reference can never be
    # fitted to this patient ("for an eGFR of 35 … 25 mg" was seen in the Step 7 smoke test).
    words = set(re.findall(r"[a-z]+", f"{question} {general_question or ''}".lower()))
    general_question = re.sub(r"\s+", " ", re.sub(r"\S*\d\S*", " ", general_question or "")).strip()
    # D65: the topics the patient's values point to, taken by code from the user's and the agent's words.
    for topic, triggers in TOPIC_HINTS.items():
        found = sorted(words & set(triggers))
        if general_question and found and topic.lower() not in general_question.lower():
            # The lab or organ NAMES are kept (not values): the search must match how documents phrase
            # the rule ("ALT/AST > 3x ULN → medical review"), which "hepatic impairment" alone missed.
            general_question += f"; {topic} for {', '.join(found)}"
    reference = None
    if reason == "patient_specific" and general_question and result["country"]:
        reference = rt.answer(general_question, mode="current", country=result["country"],
                              caller="escalate:general_reference")

    ok, detail = _record({
        "escalation_id": escalation_id, "created_at": datetime.now(timezone.utc).isoformat(), "reason": reason,
        "question": question, "general_question": general_question or None, "country": result["country"],
        "caller": caller, "team": team, "status": "OPEN",
        "general_reference_outcome": reference["outcome"] if reference else None, "run_tag": rt.run_tag(),
    })
    if not ok:
        result.update(outcome="error", answer=HANDOFF_FAILED.format(error=detail, team=team))
    else:
        template = HANDOFF_PATIENT if reason == "patient_specific" else HANDOFF_REQUEST
        result.update(outcome="escalated", answer=template.format(team=team, id=escalation_id))
        if reference and reference["outcome"] in ("answered", "partial"):
            result["answer"] += f"\n\n{GENERAL_REFERENCE_HEADER}\n{reference['answer']}"
            result["sources"] = reference.get("sources", "")
    rt.log_question(result, caller)
    return result
