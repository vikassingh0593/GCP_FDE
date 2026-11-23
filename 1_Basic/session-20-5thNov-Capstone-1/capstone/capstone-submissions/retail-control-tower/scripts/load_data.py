"""Load the sample data into BigQuery and Cloud Storage, replacing what was there.

Run from retail-control-tower/, after `python data/generate_data.py`:

    python -m scripts.load_data              # load and verify
    python -m scripts.load_data --dry-run    # show the plan; no cloud calls

Steps:
  0. Preflight   - the CSVs were generated recently and match manifest.json.
                   Loading old CSVs would make every freshness test fail.
  1. Containers  - create the dataset and bucket only if missing (safe to re-run).
  2. Tables      - load the 5 operational tables and the document register with
                   WRITE_TRUNCATE and the schema files. WRITE_TRUNCATE replaces a
                   table in one job that either fully succeeds or fully fails, so
                   a table is never empty or half-loaded (unlike TRUNCATE, then load).
  3. Docs        - sync the registered PDFs to gs://<bucket>/<prefix>/: upload new
                   or changed files (MD5 compare), then delete objects that are no
                   longer registered. Never delete-all-first: the bucket is never
                   empty. The register is the allowlist (KN-01): only files it
                   lists are uploaded, so the answer key (scenarios.md,
                   golden_questions.jsonl) and the markdown sources never leave
                   the laptop.
  4. Verify      - row counts against the manifest and the register, spot checks
                   of planted facts, and the bucket contents. Prints counts and
                   IDs only, never customer details.

Not here: parsing, chunking and embedding the PDFs (scripts/ingest_docs.py, with
Document AI), and the doc_chunks / escalations tables (created by the step that
first writes them). The PDFs and the register are built by data/build_docs.py.

If a run stops halfway, some tables may hold the new T and others the old one.
Re-run the script: every step is safe to repeat.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import config
from common.utils import fail, log, parse_utc

# Refuse CSVs older than this. Fresh inventory rows are ~10 min old at T and
# stale at INVENTORY_MAX_AGE_MINUTES, so loading older data wastes the window.
DEFAULT_MAX_DATA_AGE_MINUTES = 30

TABLE_DESCRIPTIONS = {
    "orders": "Order system extract. SENSITIVE columns: customer_name, customer_phone, "
              "shipping_address, payment_status. Freshness: extracted_at.",
    "inventory": "Stock ledger snapshot per warehouse and SKU. Freshness: snapshot_at.",
    "carrier_events": "Carrier tracking events. event_at = when it happened, received_at = when we got it.",
    "warehouse_events": "Warehouse disruptions. Empty ended_at = still ongoing.",
    "change_log": "Config and system changes by scope. Time: changed_at.",
}


# -----------------------------------------------------------------------------
# 0. Preflight: local files only
# -----------------------------------------------------------------------------

def preflight(max_age_minutes: int) -> dict:
    """Check the generated data before touching the cloud. Returns the manifest."""
    if not config.MANIFEST_FILE.exists():
        fail(f"{config.MANIFEST_FILE.relative_to(config.ROOT)} not found. Run: python data/generate_data.py")
    manifest = json.loads(config.MANIFEST_FILE.read_text(encoding="utf-8"))

    T = parse_utc(manifest["generated_at"])
    age = datetime.now(timezone.utc) - T
    if age < timedelta(0):
        fail(f"data was generated for a future time (T = {manifest['generated_at']}). "
             "Run python data/generate_data.py without --as-of.")
    if age > timedelta(minutes=max_age_minutes):
        fail(f"data is {int(age.total_seconds() // 60)} min old (T = {manifest['generated_at']}, "
             f"limit {max_age_minutes} min). Run: python data/generate_data.py")
    log("ok", f"data generated {int(age.total_seconds() // 60)} min ago (T = {manifest['generated_at']})")

    for name in config.OPERATIONAL_TABLES:
        csv_path = config.TABLES_DIR / f"{name}.csv"
        schema_path = config.SCHEMAS_DIR / f"{name}.json"
        for path in (csv_path, schema_path):
            if not path.exists():
                fail(f"missing {path.relative_to(config.ROOT)}. Run: python data/generate_data.py")
        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = sum(1 for _ in reader)
        expected = manifest["row_counts"].get(name)
        if rows != expected:
            fail(f"{name}.csv has {rows} rows but the manifest says {expected}. Re-run generate_data.py.")
        schema_columns = [c["name"] for c in json.loads(schema_path.read_text(encoding="utf-8"))]
        if header != schema_columns:
            fail(f"{name}.csv columns do not match schemas/{name}.json. Re-run generate_data.py.")
    log("ok", f"{len(config.OPERATIONAL_TABLES)} CSVs match the manifest and their schemas")
    return manifest


REGISTER_REQUIRED = ("doc_id", "version", "status", "doc_type", "title", "file_path", "media")
REGISTER_STATUSES = {"current", "superseded"}


def read_register() -> list[dict]:
    """The document register: one row per document version. Checked before anything is uploaded."""
    path = config.DOCUMENT_REGISTER_FILE
    if not path.exists():
        fail(f"{path.relative_to(config.ROOT)} not found. Run: python data/build_docs.py")
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        fail("the document register is empty")
    problems = []
    for n, row in enumerate(rows, start=2):
        missing = [c for c in REGISTER_REQUIRED if not (row.get(c) or "").strip()]
        if missing:
            problems.append(f"register line {n}: missing {', '.join(missing)}")
        if row.get("status") not in REGISTER_STATUSES:
            problems.append(f"register line {n}: status {row.get('status')!r} is not one of {sorted(REGISTER_STATUSES)}")
        if not (config.DOCS_DIR / row.get("file_path", "")).is_file():
            problems.append(f"register line {n}: file {row.get('file_path')!r} not found under data/docs/")
    keys = [(r["doc_id"], r["version"]) for r in rows]
    if len(keys) != len(set(keys)):
        problems.append("register has duplicate (doc_id, version) rows")
    if problems:
        fail("document register problems:\n  - " + "\n  - ".join(problems))
    return rows


def local_docs(register: list[dict] | None = None) -> dict[str, Path]:
    """Object name -> local PDF, for every file the register lists (the upload allowlist).

    A PDF on disk that the register doesn't list is never uploaded: it has no
    metadata, so search couldn't filter it by status or version.
    """
    register = register if register is not None else read_register()
    docs = {config.gcs_doc_path(config.DOCS_DIR / r["file_path"]): config.DOCS_DIR / r["file_path"]
            for r in register}
    registered = {p.resolve() for p in docs.values()}
    for extra in sorted(config.DOCS_DIR.rglob("*.pdf")):
        if extra.resolve() not in registered:
            log("skip", f"{extra.relative_to(config.ROOT)} is not in the register; not uploaded")
    return dict(sorted(docs.items()))


# -----------------------------------------------------------------------------
# 1. Containers
# -----------------------------------------------------------------------------

def ensure_dataset(bq) -> None:
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    # Look first, create only on NotFound: BigQuery raises Conflict (not
    # AlreadyExists) on a duplicate create, which crashed session 7 on re-run.
    try:
        dataset = bq.get_dataset(config.dataset_id())
        if dataset.location != config.BIGQUERY_LOCATION:
            fail(f"dataset {config.dataset_id()} is in {dataset.location}, lab.env says {config.BIGQUERY_LOCATION}")
        log("reuse", f"dataset {config.dataset_id()} ({dataset.location})")
    except NotFound:
        dataset = bigquery.Dataset(config.dataset_id())
        dataset.location = config.BIGQUERY_LOCATION
        dataset.description = "Retail Order Exception Control Tower (capstone 02) - vks"
        bq.create_dataset(dataset)
        log("create", f"dataset {config.dataset_id()} ({config.BIGQUERY_LOCATION})")


def ensure_bucket(gcs):
    from google.api_core.exceptions import NotFound

    try:
        bucket = gcs.get_bucket(config.GCS_BUCKET)
        log("reuse", f"bucket gs://{bucket.name} ({bucket.location})")
    except NotFound:
        bucket = gcs.bucket(config.GCS_BUCKET)
        # IAM-only permissions, and the bucket can never be made public.
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True
        bucket.iam_configuration.public_access_prevention = "enforced"
        bucket = gcs.create_bucket(bucket, location=config.GCS_LOCATION)
        log("create", f"bucket gs://{bucket.name} ({config.GCS_LOCATION})")
    return bucket


# -----------------------------------------------------------------------------
# 2. Tables
# -----------------------------------------------------------------------------

def load_tables(bq) -> None:
    from google.cloud import bigquery

    for name, table in config.OPERATIONAL_TABLES.items():
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,                                   # the header row
            schema=bq.schema_from_json(str(config.SCHEMAS_DIR / f"{name}.json")),
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            destination_table_description=TABLE_DESCRIPTIONS.get(name),
            allow_quoted_newlines=False,
            max_bad_records=0,                                     # one bad row fails the load
        )
        with (config.TABLES_DIR / f"{name}.csv").open("rb") as f:
            job = bq.load_table_from_file(f, config.table_id(table), job_config=job_config)
        job.result()                    # wait; raises if BigQuery rejected the load
        log("load", f"{config.table_id(table)}: {job.output_rows} rows (job {job.job_id})")


def load_register(bq) -> None:
    """The document register goes to BigQuery too: ingestion and search take metadata from it."""
    from google.cloud import bigquery

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=bq.schema_from_json(str(config.SCHEMAS_DIR / "document_register.json")),
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        destination_table_description="Document register: one row per runbook/postmortem version. "
                                      "Only status = 'current' documents are evidence.",
        max_bad_records=0,
    )
    table = config.table_id(config.BQ_DOCUMENT_REGISTER_TABLE)
    with config.DOCUMENT_REGISTER_FILE.open("rb") as f:
        job = bq.load_table_from_file(f, table, job_config=job_config)
    job.result()
    log("load", f"{table}: {job.output_rows} rows (job {job.job_id})")


# -----------------------------------------------------------------------------
# 3. Docs
# -----------------------------------------------------------------------------

def md5_base64(path: Path) -> str:
    """MD5 in the base64 form Cloud Storage reports."""
    return base64.b64encode(hashlib.md5(path.read_bytes()).digest()).decode("ascii")


def sync_docs(gcs, bucket, docs: dict[str, Path]) -> dict:
    prefix = f"{config.GCS_DOCS_PREFIX}/"
    remote = {b.name: b for b in gcs.list_blobs(bucket, prefix=prefix)}
    counts = {"uploaded": 0, "same": 0, "deleted": 0}

    for object_name, path in docs.items():
        existing = remote.get(object_name)
        if existing is not None and existing.md5_hash == md5_base64(path):
            counts["same"] += 1
            continue
        bucket.blob(object_name).upload_from_filename(str(path), content_type="application/pdf")
        counts["uploaded"] += 1
        log("upload", config.gcs_uri(object_name))

    # Only after every upload succeeded: remove objects that are no longer
    # registered, so a renamed or withdrawn runbook can't be found by search later.
    for object_name, blob in remote.items():
        if object_name not in docs:
            blob.delete()
            counts["deleted"] += 1
            log("delete", config.gcs_uri(object_name))

    log("docs", f"{counts['uploaded']} uploaded, {counts['same']} unchanged, {counts['deleted']} deleted")
    return counts


# -----------------------------------------------------------------------------
# 4. Verify
# -----------------------------------------------------------------------------

def verify(bq, gcs, bucket, manifest: dict, docs: dict[str, Path], register: list[dict]) -> None:
    from google.cloud import bigquery

    problems: list[str] = []

    # Row counts in BigQuery = manifest.
    for name, table in config.OPERATIONAL_TABLES.items():
        rows = bq.get_table(config.table_id(table)).num_rows
        expected = manifest["row_counts"][name]
        status = "ok" if rows == expected else "MISMATCH"
        log(status.lower() if status == "ok" else "FAIL", f"{table}: {rows} rows (manifest {expected})")
        if rows != expected:
            problems.append(f"{table} has {rows} rows, expected {expected}")

    # Spot checks: planted facts, with times measured from T (not from now).
    T = manifest["generated_at"]
    inv = config.table_id(config.OPERATIONAL_TABLES["inventory"])
    orders = config.table_id(config.OPERATIONAL_TABLES["orders"])
    sql = f"""
        SELECT
          (SELECT quantity FROM `{orders}` WHERE order_id = 'ORD-78421') AS s1_quantity,
          (SELECT available FROM `{inv}` WHERE warehouse_id = 'WH-BLR-01' AND sku = 'SKU-74512') AS s1_available,
          (SELECT TIMESTAMP_DIFF(@t, MAX(snapshot_at), MINUTE) FROM `{inv}`) AS freshest_snapshot_min,
          (SELECT TIMESTAMP_DIFF(@t, snapshot_at, MINUTE) FROM `{inv}`
             WHERE warehouse_id = 'WH-DEL-01' AND sku = 'SKU-85023') AS s7_stale_snapshot_min,
          (SELECT COUNT(*) FROM `{orders}` WHERE order_id = 'ORD-99999') AS s12_rows
    """
    job = bq.query(sql, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("t", "TIMESTAMP", parse_utc(T))]))
    r = list(job.result())[0]
    checks = [
        ("S1  ORD-78421 quantity = 40", r.s1_quantity == 40),
        ("S1  WH-BLR-01/SKU-74512 available = 7", r.s1_available == 7),
        ("freshest inventory snapshot <= 15 min before T", r.freshest_snapshot_min is not None
         and 0 <= r.freshest_snapshot_min <= 15),
        ("S7  WH-DEL-01/SKU-85023 snapshot = 2 days before T", r.s7_stale_snapshot_min == 2 * 24 * 60),
        ("S12 ORD-99999 not present", r.s12_rows == 0),
    ]
    for label, passed in checks:
        log("ok" if passed else "FAIL", label)
        if not passed:
            problems.append(f"spot check failed: {label}")

    # Register in BigQuery = register file.
    rows = bq.get_table(config.table_id(config.BQ_DOCUMENT_REGISTER_TABLE)).num_rows
    log("ok" if rows == len(register) else "FAIL",
        f"{config.BQ_DOCUMENT_REGISTER_TABLE}: {rows} rows (register file {len(register)})")
    if rows != len(register):
        problems.append(f"{config.BQ_DOCUMENT_REGISTER_TABLE} has {rows} rows, expected {len(register)}")

    # Bucket holds exactly the registered docs.
    remote_names = {b.name for b in gcs.list_blobs(bucket, prefix=f"{config.GCS_DOCS_PREFIX}/")}
    if remote_names != set(docs):
        problems.append(f"bucket has {len(remote_names)} docs, local has {len(docs)} "
                        f"(missing: {sorted(set(docs) - remote_names)}, extra: {sorted(remote_names - set(docs))})")
        log("FAIL", "bucket docs differ from the register")
    else:
        log("ok", f"bucket holds exactly the {len(docs)} registered PDFs")

    if problems:
        fail("verification found problems:\n  - " + "\n  - ".join(problems))


# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Load sample data into BigQuery and Cloud Storage.")
    parser.add_argument("--dry-run", action="store_true", help="check local files and show the plan; no cloud calls")
    parser.add_argument("--max-age-minutes", type=int, default=DEFAULT_MAX_DATA_AGE_MINUTES,
                        help=f"refuse data generated longer ago than this (default {DEFAULT_MAX_DATA_AGE_MINUTES})")
    args = parser.parse_args()

    started = time.monotonic()
    print(f"project {config.PROJECT_ID} | dataset {config.BQ_DATASET} ({config.BIGQUERY_LOCATION}) "
          f"| bucket gs://{config.GCS_BUCKET}/{config.GCS_DOCS_PREFIX}/ ({config.GCS_LOCATION})\n")

    log("step", "0. preflight")
    manifest = preflight(args.max_age_minutes)
    register = read_register()
    docs = local_docs(register)
    log("ok", f"register lists {len(register)} documents "
              f"({sum(r['status'] == 'current' for r in register)} current, "
              f"{sum(r['media'] == 'pdf_scan' for r in register)} scanned); all files present")

    if args.dry_run:
        log("plan", f"tables: {', '.join(config.table_id(t) for t in config.OPERATIONAL_TABLES.values())}")
        log("plan", f"register -> {config.table_id(config.BQ_DOCUMENT_REGISTER_TABLE)}")
        log("plan", f"docs: {len(docs)} PDFs -> gs://{config.GCS_BUCKET}/{config.GCS_DOCS_PREFIX}/")
        for object_name in docs:
            print(f"           {object_name}")
        print("\nDry run: nothing was sent to the cloud.")
        return

    from google.cloud import bigquery, storage

    bq = bigquery.Client(project=config.PROJECT_ID, location=config.BIGQUERY_LOCATION)
    gcs = storage.Client(project=config.PROJECT_ID)

    log("step", "1. dataset and bucket")
    ensure_dataset(bq)
    bucket = ensure_bucket(gcs)

    log("step", "2. tables (WRITE_TRUNCATE)")
    load_tables(bq)
    load_register(bq)

    log("step", "3. docs sync")
    sync_docs(gcs, bucket, docs)

    log("step", "4. verify")
    verify(bq, gcs, bucket, manifest, docs, register)

    print(f"\nLOAD COMPLETE in {time.monotonic() - started:.1f}s. T = {manifest['generated_at']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted. Re-run the script: every step is safe to repeat.")
