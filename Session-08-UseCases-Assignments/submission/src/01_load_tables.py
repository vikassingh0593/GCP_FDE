"""Load the document registry and the adverse-event CSV into BigQuery.

Creates or replaces, in dataset BQ_DATASET:
- table `documents`        cleaned document_registry.csv + metadata_supplement.csv
- table `adverse_events`   adverse_event_registry.csv, values as they are
- view  `v_documents`      the registry for text-to-SQL, plus an `is_current` flag
- view  `v_adverse_events` one row per study + event

Why tables and not embeddings: these values are used as filters (status,
country, dates) and as exact numbers (AE rates). Vector search finds
*similar*; only SQL finds *equal*.

Why a full snapshot (WRITE_TRUNCATE) and not MERGE: the registry is the whole
truth every time, so each load replaces the table in one atomic job. Chunks
arrive a few at a time and use MERGE (Step 2.4). Both are safe to re-run,
unlike session-07's delete-then-create, which left no table if it crashed
in between.

Data-quality checks run before anything is loaded; the script stops if any
check fails.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from google.cloud import bigquery

from health import Health
from policy import LIFECYCLE, STATUS_MAP, TIMEZONE_OFFSETS, VERSIONED_TYPES, normalize_country
from config import (
    AE_REGISTRY_CSV,
    BQ_AE_TABLE,
    BQ_DATASET,
    BQ_DOCUMENTS_TABLE,
    DOCUMENT_REGISTRY_CSV,
    GCS_BUCKET,
    GCS_RAW_PREFIX,
    OVERRIDES_CSV,
    PROJECT_ID,
    SOURCE_FILES,
    SUPPLEMENT_CSV,
    gcs_uri,
    table_id,
)


# Business rules come from policy.py (one reviewable copy); corpus facts come
# from data files: the registry, metadata_supplement.csv (files the registry
# lacks) and metadata_overrides.csv (facts stated in a document but missing
# from the registry, e.g. the bulletin's effective time). Step 5a, D44.
ALLOWED_STATUS = set(LIFECYCLE)


def read_effective_times() -> dict:
    """document_id → exact effective time (UTC) from metadata_overrides.csv.

    "10:00 CET" is taken literally with policy.TIMEZONE_OFFSETS (assumption A10).
    """
    if not OVERRIDES_CSV.exists():
        return {}
    with OVERRIDES_CSV.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("effective_time") or "").strip()]
    times = {}
    for r in rows:
        match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*([A-Za-z]+)?\s*", r["effective_time"])
        if not match:
            raise SystemExit(f"metadata_overrides.csv: cannot read time {r['effective_time']!r} for {r['document_id']}")
        hour, minute, zone = int(match.group(1)), int(match.group(2)), (match.group(3) or "UTC").upper()
        if zone not in TIMEZONE_OFFSETS:
            raise SystemExit(f"metadata_overrides.csv: unknown time zone {zone!r} for {r['document_id']}")
        times[r["document_id"].strip()] = (hour, minute, TIMEZONE_OFFSETS[zone])
    return times


# -----------------------------------------------------------------------------
# Read and clean
# -----------------------------------------------------------------------------

def _utc_date(value: str) -> datetime:
    """A date with no time means 00:00 UTC that day (decision D3)."""
    return datetime.fromisoformat(value.strip()).replace(tzinfo=timezone.utc)


_EFFECTIVE_TIMES: dict | None = None


def _effective_from(document_id: str, date: str) -> datetime:
    """The registry date at 00:00 UTC (D3), or the exact time from metadata_overrides.csv."""
    global _EFFECTIVE_TIMES
    if _EFFECTIVE_TIMES is None:
        _EFFECTIVE_TIMES = read_effective_times()
    base = _utc_date(date)
    if document_id in _EFFECTIVE_TIMES:
        hour, minute, offset = _EFFECTIVE_TIMES[document_id]
        return base.replace(hour=hour, minute=minute) - timedelta(hours=offset)
    return base


def _clean_document(row: dict, source: str) -> dict:
    """Normalize one registry or supplement row into a `documents` row."""
    document_id = row["document_id"].strip()
    filename = row["filename"].strip()
    raw_status = row["status"].strip().upper()
    countries = [
        normalize_country(c)
        for c in row["country"].split("|")
        if c.strip()
    ]
    valid_to = row.get("valid_to", "").strip()

    return {
        "document_id": document_id,
        "title": filename.rsplit(".", 1)[0].replace("_", " "),
        "filename": filename,
        "product": row["product"].strip(),
        "countries": countries,
        "status": STATUS_MAP.get(raw_status, raw_status),
        "raw_status": raw_status,
        "version": row["version"].strip(),
        "effective_from": _effective_from(document_id, row["effective_date"]),
        "valid_to": _utc_date(valid_to) if valid_to else None,
        "authority": row["authority"].strip(),
        "document_type": row["type"].strip(),
        "gcs_uri": gcs_uri(filename),
        # Opens only for users with read access to the bucket (no signed URLs).
        "view_url": f"https://storage.cloud.google.com/{GCS_BUCKET}/{GCS_RAW_PREFIX}/{filename}",
        "source": source,
        "notes": row.get("notes", "").strip() or None,
    }


def _derive_valid_to(documents: list[dict]) -> None:
    """Set `valid_to` from the next version of the same versioned document.

    The registry has no "supersedes" column (only page 1 of v4.2 says it), so
    the rule rebuilds it: same product + same countries + versioned type,
    ordered by effective date. Rows that already carry `valid_to` keep it.
    """
    families = defaultdict(list)
    for doc in documents:
        if doc["document_type"] in VERSIONED_TYPES:
            key = (doc["product"], tuple(sorted(doc["countries"])), doc["document_type"])
            families[key].append(doc)

    for family in families.values():
        family.sort(key=lambda d: d["effective_from"])
        for older, newer in zip(family, family[1:]):
            if older["valid_to"] is None:
                older["valid_to"] = newer["effective_from"]


def read_documents() -> list[dict]:
    """Registry rows plus supplement rows, cleaned, with `valid_to` derived."""
    with DOCUMENT_REGISTRY_CSV.open(newline="", encoding="utf-8") as f:
        documents = [_clean_document(r, "registry") for r in csv.DictReader(f)]
    with SUPPLEMENT_CSV.open(newline="", encoding="utf-8") as f:
        documents += [_clean_document(r, "supplement") for r in csv.DictReader(f)]
    _derive_valid_to(documents)
    return documents


def read_adverse_events() -> list[dict]:
    """AE rows with numeric rates; values are not changed."""
    with AE_REGISTRY_CSV.open(newline="", encoding="utf-8") as f:
        return [
            {
                "study_id": r["study_id"].strip(),
                "event": r["event"].strip(),
                "treatment_rate_pct": float(r["treatment_rate_pct"]),
                "control_rate_pct": float(r["control_rate_pct"]),
                "renal_subgroup": r["renal_subgroup"].strip(),
                "source_file": AE_REGISTRY_CSV.name,
            }
            for r in csv.DictReader(f)
        ]


# -----------------------------------------------------------------------------
# Data-quality checks: collect every problem, then stop if there are any
# -----------------------------------------------------------------------------

def check_quality(documents: list[dict], adverse_events: list[dict], health: Health) -> None:
    """Fail the run before loading if the data breaks an assumption we rely on.

    Every check is also recorded in BigQuery `pipeline_health` (pass or fail).
    """
    ids = [d["document_id"] for d in documents]
    files = [d["filename"] for d in documents]

    rates = defaultdict(set)
    for r in adverse_events:
        rates[(r["study_id"], r["event"])].add((r["treatment_rate_pct"], r["control_rate_pct"]))

    studies = {r["study_id"] for r in adverse_events}
    events = {r["event"] for r in adverse_events}
    subgroups = {r["renal_subgroup"] for r in adverse_events}
    expected_rows = len(studies) * len(events) * len(subgroups)

    bad_status = [d["document_id"] for d in documents if d["status"] not in ALLOWED_STATUS]
    no_country = [d["document_id"] for d in documents if not d["countries"]]
    # A document replaced by a newer version must not still be APPROVED.
    stale_approved = [d["document_id"] for d in documents
                      if d["document_type"] in VERSIONED_TYPES and d["valid_to"] and d["status"] == "APPROVED"]
    varying = [k for k, v in rates.items() if len(v) > 1]
    unknown_studies = sorted({r["study_id"] for r in adverse_events} - set(ids))
    missing = sorted(set(SOURCE_FILES) - set(files))
    extra = sorted(set(files) - set(SOURCE_FILES))

    # (check name, passed?, measured value, threshold, detail when it fails)
    checks = [
        ("document_ids_unique", len(ids) == len(set(ids)), len(ids), "no duplicates",
         f"duplicates: {sorted(i for i in ids if ids.count(i) > 1)}"),
        ("documents_match_allowlist", not missing and not extra, len(files), f"= {len(SOURCE_FILES)} files",
         f"missing={missing} extra={extra}"),
        ("status_in_lifecycle", not bad_status, len(bad_status), "= 0", f"outside the lifecycle: {bad_status}"),
        ("countries_present", not no_country, len(no_country), "= 0", f"no country: {no_country}"),
        ("superseded_consistency", not stale_approved, len(stale_approved), "= 0",
         f"has a successor but is still APPROVED: {stale_approved}"),
        # A complete grid: every study × event × renal subgroup appears exactly once (no fixed count).
        ("ae_complete_grid", len(adverse_events) == expected_rows, len(adverse_events),
         f"= studies × events × subgroups = {expected_rows}", f"got {len(adverse_events)}"),
        ("ae_rates_constant_across_subgroups", not varying, len(rates), "1 rate pair per study+event",
         f"rates differ for {varying}"),
        ("ae_studies_registered", not unknown_studies, len(unknown_studies), "= 0",
         f"study IDs not in documents: {unknown_studies}"),
    ]
    problems = []
    for name, ok, value, threshold, detail in checks:
        health.record(name, "pass" if ok else "fail", value=value, threshold=threshold,
                      details=None if ok else detail)
        if not ok:
            problems.append(f"{name}: {detail}")

    if problems:
        health.save()
        raise SystemExit("Data-quality check FAILED:\n  - " + "\n  - ".join(problems))
    print(f"[check] {len(documents)} documents, {len(adverse_events)} AE rows, "
          f"{len(rates)} study+event pairs: all checks passed")


# -----------------------------------------------------------------------------
# Load to BigQuery
# -----------------------------------------------------------------------------

DOCUMENTS_SCHEMA = [
    bigquery.SchemaField("document_id", "STRING", "REQUIRED", description="Controlled document ID, e.g. DE-AX17-LBL-042. Cite this."),
    bigquery.SchemaField("title", "STRING", description="Readable title derived from the file name."),
    bigquery.SchemaField("filename", "STRING", "REQUIRED", description="Original file name in the corpus."),
    bigquery.SchemaField("product", "STRING", "REQUIRED", description="Product, e.g. AX-17. A hard filter: products are never mixed."),
    bigquery.SchemaField("countries", "STRING", "REPEATED", description="Jurisdictions the document applies to. GLOBAL = scientific evidence anywhere, regulatory guidance nowhere."),
    bigquery.SchemaField("status", "STRING", "REQUIRED", description="Normalized lifecycle status used for filtering: DRAFT, REVIEW, APPROVED, SUPERSEDED, WITHDRAWN."),
    bigquery.SchemaField("raw_status", "STRING", description="Status exactly as in the source registry, e.g. FINAL (kept for audit)."),
    bigquery.SchemaField("version", "STRING", description="Document version, e.g. 4.2."),
    bigquery.SchemaField("effective_from", "TIMESTAMP", "REQUIRED", description="When the document took effect (UTC)."),
    bigquery.SchemaField("valid_to", "TIMESTAMP", description="When it stopped applying (UTC, exclusive). NULL = no successor."),
    bigquery.SchemaField("authority", "STRING", description="SAFETY_BULLETIN, REGULATORY_LABEL, CLINICAL_STUDY or SAFETY_LETTER. Orders evidence; never excludes it."),
    bigquery.SchemaField("document_type", "STRING", description="LABEL, STUDY, BULLETIN or LETTER."),
    bigquery.SchemaField("gcs_uri", "STRING", description="Location of the original file in Cloud Storage."),
    bigquery.SchemaField("view_url", "STRING", description="Link that opens the original file for users with read access to the bucket."),
    bigquery.SchemaField("source", "STRING", description="registry, or supplement (our assumption for files with no registry row)."),
    bigquery.SchemaField("notes", "STRING", description="Why a supplement row exists and what was assumed."),
    bigquery.SchemaField("loaded_at", "TIMESTAMP", description="When this snapshot was loaded."),
]

AE_SCHEMA = [
    bigquery.SchemaField("study_id", "STRING", "REQUIRED", description="Clinical study ID, e.g. HN-204."),
    bigquery.SchemaField("event", "STRING", "REQUIRED", description="Adverse event name, e.g. nausea."),
    bigquery.SchemaField("treatment_rate_pct", "FLOAT64", description="Percent of AX-17 participants with the event."),
    bigquery.SchemaField("control_rate_pct", "FLOAT64", description="Percent of control participants with the event."),
    bigquery.SchemaField("renal_subgroup", "STRING", description="Renal stratum label. Rates repeat identically across the 4 subgroups: never sum or average across them; use v_adverse_events."),
    bigquery.SchemaField("source_file", "STRING", description="CSV the row came from."),
    bigquery.SchemaField("loaded_at", "TIMESTAMP", description="When this snapshot was loaded."),
]


def _to_json(row: dict) -> dict:
    """BigQuery JSON loads take timestamps as ISO strings."""
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()}


def load_snapshot(client: bigquery.Client, table: str, rows: list[dict], schema, description: str) -> None:
    """Replace a table with a full snapshot in one atomic load job."""
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        destination_table_description=description,
    )
    client.load_table_from_json([_to_json(r) for r in rows], table_id(table), job_config=job_config).result()
    print(f"[load]  {table_id(table)}: {len(rows)} rows")


def create_views(client: bigquery.Client) -> None:
    """Curated views: the only objects text_to_sql may read (never `chunks`)."""
    dataset = f"`{PROJECT_ID}.{BQ_DATASET}`"
    statements = {
        "v_documents": f"""
            CREATE OR REPLACE VIEW {dataset}.v_documents (
              document_id OPTIONS(description = 'Controlled document ID. Cite this.'),
              title, product, countries,
              status OPTIONS(description = 'Normalized status: APPROVED, SUPERSEDED, ...'),
              raw_status, version,
              effective_from OPTIONS(description = 'When it took effect (UTC).'),
              valid_to OPTIONS(description = 'When it stopped applying (UTC, exclusive).'),
              authority, document_type, view_url,
              is_current OPTIONS(description = 'TRUE if APPROVED and in effect right now. SQL answers about documents must state the status.')
            )
            OPTIONS(description = 'Cleaned document registry for text-to-SQL. Metadata only: never use it as current guidance.')
            AS
            SELECT
              document_id, title, product, countries, status, raw_status, version,
              effective_from, valid_to, authority, document_type, view_url,
              status = 'APPROVED'
                AND effective_from <= CURRENT_TIMESTAMP()
                AND (valid_to IS NULL OR valid_to > CURRENT_TIMESTAMP()) AS is_current
            FROM {dataset}.{BQ_DOCUMENTS_TABLE}
        """,
        "v_adverse_events": f"""
            CREATE OR REPLACE VIEW {dataset}.v_adverse_events (
              study_id OPTIONS(description = 'Clinical study ID, e.g. HN-204.'),
              event OPTIONS(description = 'Adverse event name.'),
              treatment_rate_pct OPTIONS(description = 'Percent of AX-17 participants with the event (per study).'),
              control_rate_pct OPTIONS(description = 'Percent of control participants with the event (per study).')
            )
            OPTIONS(description = 'One row per study + event. Use this, not adverse_events, so the 4 repeated subgroup rows cannot inflate a SUM or AVG.')
            AS
            SELECT DISTINCT study_id, event, treatment_rate_pct, control_rate_pct
            FROM {dataset}.{BQ_AE_TABLE}
        """,
    }
    for name, sql in statements.items():
        client.query(sql).result()
        print(f"[view]  {PROJECT_ID}.{BQ_DATASET}.{name}")


def show_result(client: bigquery.Client) -> int:
    """Print what landed, so the run can be checked by eye; return the view's row count."""
    rows = client.query(f"""
        SELECT document_id, status, raw_status, ARRAY_TO_STRING(countries, ', ') AS countries,
               FORMAT_TIMESTAMP('%F %R', effective_from) AS effective_utc,
               IFNULL(FORMAT_TIMESTAMP('%F', valid_to), '-') AS valid_to,
               is_current
        FROM `{PROJECT_ID}.{BQ_DATASET}.v_documents`
        ORDER BY document_type, effective_from
    """).result()
    print("\n  document_id            status      raw         countries                  effective (UTC)   valid_to    current")
    for r in rows:
        print(f"  {r.document_id:22} {r.status:11} {r.raw_status:11} {r.countries:26} {r.effective_utc:17} {r.valid_to:11} {r.is_current}")

    ae = list(client.query(f"SELECT COUNT(*) AS n FROM `{PROJECT_ID}.{BQ_DATASET}.v_adverse_events`").result())[0].n
    print(f"\n  v_adverse_events: {ae} rows (one per study + event)")
    return ae


def main() -> None:
    """Read, check, load, create views, show the result."""
    health = Health("load_tables")
    documents = read_documents()
    adverse_events = read_adverse_events()
    check_quality(documents, adverse_events, health)

    loaded_at = datetime.now(timezone.utc)
    for row in documents + adverse_events:
        row["loaded_at"] = loaded_at

    client = bigquery.Client(project=PROJECT_ID)
    load_snapshot(client, BQ_DOCUMENTS_TABLE, documents, DOCUMENTS_SCHEMA,
                  "Cleaned document registry (+ supplement). Source of truth for status, country and dates.")
    load_snapshot(client, BQ_AE_TABLE, adverse_events, AE_SCHEMA,
                  "Adverse-event rates per study, as delivered. Use v_adverse_events for analysis.")
    create_views(client)
    ae_view_rows = show_result(client)

    health.record("documents_loaded", "pass", value=len(documents))
    health.record("adverse_events_loaded", "pass", value=len(adverse_events))
    pairs = len({(r["study_id"], r["event"]) for r in adverse_events})
    health.record("v_adverse_events_rows", "pass" if ae_view_rows == pairs else "fail", value=ae_view_rows,
                  threshold=f"= {pairs} (one per study + event)")
    health.save()


if __name__ == "__main__":
    main()
