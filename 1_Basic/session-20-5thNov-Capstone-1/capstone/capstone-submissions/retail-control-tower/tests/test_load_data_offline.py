"""scripts/load_data.py without the cloud: fake BigQuery and Cloud Storage clients.

What these prove offline: the preflight refuses bad data, the document register
is checked and is the upload allowlist, tables load with WRITE_TRUNCATE + schema,
docs are deleted only after uploads, and verify fails on a mismatch. What they cannot prove (run the real
load for that): permissions, locations, and that BigQuery accepts the CSVs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import config
from conftest import ROOT, load_generate_data
from scripts import load_data

gd = load_generate_data()


# -----------------------------------------------------------------------------
# Fresh generated data in a temp folder; config points at it for the test
# -----------------------------------------------------------------------------

@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    tables, schemas = tmp_path / "tables", tmp_path / "schemas"
    monkeypatch.setattr(gd, "TABLES_DIR", tables)
    monkeypatch.setattr(gd, "SCHEMAS_DIR", schemas)
    monkeypatch.setattr(gd, "DATA_DIR", tmp_path)
    T = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=2)
    gd.write_outputs(gd.build_tables(T), T, as_of_given=False)

    monkeypatch.setattr(config, "TABLES_DIR", tables)
    monkeypatch.setattr(config, "SCHEMAS_DIR", schemas)
    monkeypatch.setattr(config, "MANIFEST_FILE", tables / "manifest.json")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    return tmp_path


def _rewrite_manifest(data_dir: Path, **changes) -> None:
    path = data_dir / "tables" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(changes)
    path.write_text(json.dumps(manifest))


def _fmt(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# -----------------------------------------------------------------------------
# 0. Preflight
# -----------------------------------------------------------------------------

def test_preflight_accepts_fresh_data(data_dir):
    manifest = load_data.preflight(max_age_minutes=30)
    assert manifest["row_counts"]["orders"] == 24


def test_preflight_rejects_old_data(data_dir):
    _rewrite_manifest(data_dir, generated_at=_fmt(datetime.now(timezone.utc) - timedelta(hours=2)))
    with pytest.raises(SystemExit, match="min old"):
        load_data.preflight(max_age_minutes=30)


def test_preflight_rejects_future_data(data_dir):
    _rewrite_manifest(data_dir, generated_at=_fmt(datetime.now(timezone.utc) + timedelta(hours=1)))
    with pytest.raises(SystemExit, match="future"):
        load_data.preflight(max_age_minutes=30)


def test_preflight_rejects_row_count_mismatch(data_dir):
    csv_path = data_dir / "tables" / "orders.csv"
    lines = csv_path.read_text().splitlines(keepends=True)
    csv_path.write_text("".join(lines[:-1]))                      # drop one row
    with pytest.raises(SystemExit, match="orders.csv has 23 rows"):
        load_data.preflight(max_age_minutes=30)


def test_preflight_rejects_column_mismatch(data_dir):
    csv_path = data_dir / "tables" / "inventory.csv"
    text = csv_path.read_text()
    csv_path.write_text(text.replace("snapshot_at", "snapshot_time", 1))
    with pytest.raises(SystemExit, match="columns do not match"):
        load_data.preflight(max_age_minutes=30)


def test_preflight_rejects_missing_manifest(data_dir):
    (data_dir / "tables" / "manifest.json").unlink()
    with pytest.raises(SystemExit, match="not found"):
        load_data.preflight(max_age_minutes=30)


# -----------------------------------------------------------------------------
# Document register and upload allowlist
# -----------------------------------------------------------------------------

def test_register_is_valid():
    register = load_data.read_register()
    assert len(register) == 13
    assert sum(r["status"] == "superseded" for r in register) == 1          # RB-ALLOC-002 v2
    assert sum(r["media"] == "pdf_scan" for r in register) == 1             # PM-2025-052
    assert {r["doc_type"] for r in register} == {"runbook", "postmortem"}


def test_only_registered_pdfs_are_uploaded_never_the_answer_key():
    docs = load_data.local_docs()
    assert len(docs) == 13
    assert all(name.startswith(f"{config.GCS_DOCS_PREFIX}/") and name.endswith(".pdf") for name in docs)
    assert not any("scenarios" in n or "golden" in n or "register" in n or "docs_source" in n for n in docs)
    assert sum("/runbooks/" in n for n in docs) == 7 and sum("/postmortems/" in n for n in docs) == 6


@pytest.fixture
def docs_copy(tmp_path, monkeypatch):
    """A writable copy of data/docs/, with config pointed at it."""
    import shutil
    docs = tmp_path / "docs"
    shutil.copytree(config.DOCS_DIR, docs)
    monkeypatch.setattr(config, "DOCS_DIR", docs)
    monkeypatch.setattr(config, "DOCUMENT_REGISTER_FILE", docs / "document_register.csv")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    return docs


def test_register_rejects_a_missing_file(docs_copy):
    (docs_copy / "runbooks" / "rb-car-003-carrier-delay.pdf").unlink()
    with pytest.raises(SystemExit, match="rb-car-003-carrier-delay.pdf' not found"):
        load_data.read_register()


def test_register_rejects_an_unknown_status(docs_copy):
    path = docs_copy / "document_register.csv"
    path.write_text(path.read_text().replace(",current,", ",draft,", 1))
    with pytest.raises(SystemExit, match="status 'draft'"):
        load_data.read_register()


def test_register_missing_fails_clearly(docs_copy):
    (docs_copy / "document_register.csv").unlink()
    with pytest.raises(SystemExit, match="build_docs.py"):
        load_data.read_register()


def test_unregistered_pdf_is_never_uploaded(docs_copy):
    (docs_copy / "runbooks" / "rb-unreviewed-draft.pdf").write_bytes(b"%PDF-1.4 draft")
    docs = load_data.local_docs()
    assert not any("rb-unreviewed-draft" in name for name in docs) and len(docs) == 13


# -----------------------------------------------------------------------------
# 2. Tables (fake BigQuery client)
# -----------------------------------------------------------------------------

class FakeJob:
    def __init__(self, rows: int):
        self.output_rows, self.job_id, self.waited = rows, "job-test", False

    def result(self):
        self.waited = True
        return self


class FakeBigQuery:
    def __init__(self):
        self.loads: list[tuple[str, object, FakeJob]] = []

    def schema_from_json(self, path):
        from google.cloud import bigquery
        return [bigquery.SchemaField.from_api_repr(f) for f in json.loads(Path(path).read_text())]

    def load_table_from_file(self, file_obj, table_id, job_config):
        rows = file_obj.read().decode().count("\n") - 1          # minus the header
        job = FakeJob(rows)
        self.loads.append((table_id, job_config, job))
        return job


def test_tables_load_with_truncate_schema_and_wait(data_dir):
    from google.cloud import bigquery

    bq = FakeBigQuery()
    load_data.load_tables(bq)
    assert [t for t, _, _ in bq.loads] == [config.table_id(t) for t in config.OPERATIONAL_TABLES.values()]
    for table_id, job_config, job in bq.loads:
        assert job_config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE
        assert job_config.skip_leading_rows == 1
        assert job_config.max_bad_records == 0
        assert job_config.schema, f"{table_id}: no explicit schema"
        assert job.waited, f"{table_id}: job.result() not called"


# -----------------------------------------------------------------------------
# 3. Docs sync (fake Cloud Storage)
# -----------------------------------------------------------------------------

class FakeBlob:
    def __init__(self, store, name, md5=None):
        self.store, self.name, self.md5_hash = store, name, md5

    def upload_from_filename(self, path, content_type=None):
        self.md5_hash = load_data.md5_base64(Path(path))
        self.store.objects[self.name] = self
        self.store.calls.append(("upload", self.name, content_type))

    def delete(self):
        self.store.objects.pop(self.name)
        self.store.calls.append(("delete", self.name, None))


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, FakeBlob] = {}
        self.calls: list[tuple] = []

    def list_blobs(self, bucket, prefix):
        return [b for n, b in list(self.objects.items()) if n.startswith(prefix)]

    def blob(self, name):                                         # acts as the bucket too
        return FakeBlob(self, name)


def test_docs_sync_uploads_skips_and_deletes_in_safe_order():
    docs = load_data.local_docs()
    store = FakeStorage()
    unchanged = next(iter(docs))
    store.objects[unchanged] = FakeBlob(store, unchanged, load_data.md5_base64(docs[unchanged]))
    orphan = f"{config.GCS_DOCS_PREFIX}/runbooks/old-renamed-runbook.md"
    store.objects[orphan] = FakeBlob(store, orphan, "stale")
    outside = "other-prefix/keep-me.md"
    store.objects[outside] = FakeBlob(store, outside, "x")

    counts = load_data.sync_docs(store, store, docs)

    assert counts == {"uploaded": len(docs) - 1, "same": 1, "deleted": 1}
    assert set(store.objects) == set(docs) | {outside}            # objects outside the prefix untouched
    kinds = [c[0] for c in store.calls]
    assert kinds.index("delete") > max(i for i, k in enumerate(kinds) if k == "upload")
    assert all(ct == "application/pdf" for kind, _, ct in store.calls if kind == "upload")

    store.calls.clear()
    again = load_data.sync_docs(store, store, docs)               # second run: nothing to do
    assert again == {"uploaded": 0, "same": len(docs), "deleted": 0} and not store.calls


# -----------------------------------------------------------------------------
# 4. Verify (fake BigQuery answers)
# -----------------------------------------------------------------------------

class FakeVerifyBigQuery:
    def __init__(self, counts: dict[str, int], spot: dict):
        self.counts, self.spot = counts, spot

    def get_table(self, table_id):
        return SimpleNamespace(num_rows=self.counts[table_id.rsplit(".", 1)[1]])

    def query(self, sql, job_config=None):
        return SimpleNamespace(result=lambda: [SimpleNamespace(**self.spot)])


GOOD_SPOT = {"s1_quantity": 40, "s1_available": 7, "freshest_snapshot_min": 9,
             "s7_stale_snapshot_min": 2880, "s12_rows": 0}


def _verify(counts, spot, register_rows: int = 13):
    manifest = {"generated_at": "2026-11-22T03:30:00Z",
                "row_counts": {"orders": 24, "inventory": 17, "carrier_events": 25,
                               "warehouse_events": 4, "change_log": 4}}
    register = load_data.read_register()
    docs = load_data.local_docs(register)
    store = FakeStorage()
    for name, path in docs.items():
        store.objects[name] = FakeBlob(store, name, load_data.md5_base64(path))
    table_counts = {config.OPERATIONAL_TABLES[k]: v for k, v in counts.items()}
    table_counts[config.BQ_DOCUMENT_REGISTER_TABLE] = register_rows
    bq = FakeVerifyBigQuery(table_counts, spot)
    load_data.verify(bq, store, store, manifest, docs, register)


def test_verify_passes_when_everything_matches():
    _verify({"orders": 24, "inventory": 17, "carrier_events": 25, "warehouse_events": 4, "change_log": 4}, GOOD_SPOT)


def test_verify_fails_on_row_count_mismatch():
    with pytest.raises(SystemExit, match="orders has 23 rows"):
        _verify({"orders": 23, "inventory": 17, "carrier_events": 25, "warehouse_events": 4, "change_log": 4},
                GOOD_SPOT)


def test_verify_fails_when_the_register_table_is_short():
    with pytest.raises(SystemExit, match="document_register has 12 rows"):
        _verify({"orders": 24, "inventory": 17, "carrier_events": 25, "warehouse_events": 4, "change_log": 4},
                GOOD_SPOT, register_rows=12)


def test_verify_fails_when_a_planted_fact_is_wrong():
    with pytest.raises(SystemExit, match="S7"):
        _verify({"orders": 24, "inventory": 17, "carrier_events": 25, "warehouse_events": 4, "change_log": 4},
                {**GOOD_SPOT, "s7_stale_snapshot_min": 10})


# -----------------------------------------------------------------------------
# Dry run end to end (no cloud)
# -----------------------------------------------------------------------------

def test_dry_run_makes_no_cloud_calls(tmp_path):
    result = subprocess.run([sys.executable, "-m", "scripts.load_data", "--dry-run", "--max-age-minutes", "10000000"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "nothing was sent to the cloud" in result.stdout
