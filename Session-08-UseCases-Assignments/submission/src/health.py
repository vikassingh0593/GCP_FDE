"""Health monitor: record every check as one row in BigQuery `pipeline_health`.

A check printed to the screen is seen once and forgotten. Stored on every run,
the same check shows trends: a chunk count that drops, a faithfulness
difference that appears, a time-to-searchable that grows. The health report
(Step 8) and, in production, a Looker Studio dashboard and Cloud Monitoring
alerts read this table.

Usage inside a script:
    health = Health("parse_gate")
    health.record("junk_ratio", "pass", value=0.0, threshold="<= 0.15", document_id="HN-204")
    health.save()

All scripts started by run_ingestion.py share one run ID (environment variable
MEDEVIDENCE_RUN_ID), so one pipeline run can be read as a whole. A local copy
of every row is appended to output/health/<run_id>.jsonl.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from google.cloud import bigquery

from config import OUTPUT_DIR, PROJECT_ID, table_id


HEALTH_TABLE = "pipeline_health"

SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", "REQUIRED", description="One pipeline run; shared by every script that run_ingestion.py starts."),
    bigquery.SchemaField("recorded_at", "TIMESTAMP", "REQUIRED", description="When the check ran (UTC)."),
    bigquery.SchemaField("stage", "STRING", "REQUIRED", description="load_tables, parse_gate, embed_load, verify, index, eval, ..."),
    bigquery.SchemaField("check", "STRING", "REQUIRED", description="Name of the check, e.g. faithfulness_table_diffs."),
    bigquery.SchemaField("document_id", "STRING", description="Document the check is about; NULL for corpus-level checks."),
    bigquery.SchemaField("status", "STRING", "REQUIRED", description="pass, warn or fail."),
    bigquery.SchemaField("value", "FLOAT64", description="Measured value, e.g. a count, ratio or seconds."),
    bigquery.SchemaField("threshold", "STRING", description="What the value is compared with, e.g. '<= 0.15'."),
    bigquery.SchemaField("details", "STRING", description="Human-readable explanation."),
]

STATUSES = {"pass", "warn", "fail"}


def current_run_id() -> str:
    """The shared run ID, or a new one for a script started on its own."""
    run_id = os.getenv("MEDEVIDENCE_RUN_ID")
    if not run_id:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        os.environ["MEDEVIDENCE_RUN_ID"] = run_id
    return run_id


class Health:
    """Collects check results for one stage and writes them in one load job."""

    def __init__(self, stage: str):
        self.stage = stage
        self.run_id = current_run_id()
        self.rows: list[dict] = []

    def record(self, check: str, status: str, value=None, threshold: str | None = None,
               document_id: str | None = None, details: str | None = None) -> None:
        """Add one check result (not written until save())."""
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, got {status!r}")
        self.rows.append({
            "run_id": self.run_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "stage": self.stage,
            "check": check,
            "document_id": document_id,
            "status": status,
            "value": None if value is None else float(value),
            "threshold": threshold,
            "details": details,
        })

    def save(self) -> None:
        """Append the rows to BigQuery (table created on first use) and to a local file."""
        if not self.rows:
            return
        local = OUTPUT_DIR / "health" / f"{self.run_id}.jsonl"
        local.parent.mkdir(parents=True, exist_ok=True)
        with local.open("a", encoding="utf-8") as f:
            for row in self.rows:
                f.write(json.dumps(row) + "\n")

        job_config = bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
        )
        bigquery.Client(project=PROJECT_ID).load_table_from_json(
            self.rows, table_id(HEALTH_TABLE), job_config=job_config
        ).result()

        counts = {s: sum(r["status"] == s for r in self.rows) for s in ("pass", "warn", "fail")}
        print(f"[health] {self.stage}: {len(self.rows)} checks recorded "
              f"(pass {counts['pass']}, warn {counts['warn']}, fail {counts['fail']}) · run {self.run_id}")
        self.rows = []
