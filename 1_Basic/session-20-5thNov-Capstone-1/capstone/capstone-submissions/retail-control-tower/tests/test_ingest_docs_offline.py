"""scripts/ingest_docs.py without the cloud: options, target table, register checks."""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from types import SimpleNamespace

import pytest

from common import config
from conftest import ROOT
from scripts import ingest_docs


def test_default_settings_write_the_main_table():
    args = ingest_docs.parse_args([])
    assert args.table == config.BQ_DOC_CHUNKS_TABLE


def test_experiments_never_overwrite_the_main_table():
    assert ingest_docs.parse_args(["--chunk-size", "256"]).table == f"{config.BQ_DOC_CHUNKS_TABLE}_cs256_d{config.EMBEDDING_DIMENSION}"
    assert ingest_docs.parse_args(["--dimension", "3072"]).table == f"{config.BQ_DOC_CHUNKS_TABLE}_cs{config.CHUNK_SIZE}_d3072"
    assert ingest_docs.parse_args(["--chunk-size", "256", "--table", "mine"]).table == "mine"


class FakeBigQuery:
    def __init__(self, rows=None, missing=False):
        self.rows, self.missing = rows or [], missing

    def query(self, sql):
        if self.missing:
            from google.api_core.exceptions import NotFound
            raise NotFound("table not found")
        return SimpleNamespace(result=lambda: [SimpleNamespace(items=lambda r=r: r.items()) for r in self.rows])


def _row(**overrides):
    row = {"doc_id": "RB-CAR-003", "version": "4", "status": "current", "doc_type": "runbook",
           "title": "Carrier delay", "file_path": "runbooks/rb-car-003-carrier-delay.pdf", "media": "pdf_text",
           "effective_date": date(2026, 2, 15)}
    row.update(overrides)
    return row


def test_register_read_from_bigquery():
    rows = ingest_docs.read_register(FakeBigQuery([_row(), _row(doc_id="PM-2025-052", media="pdf_scan",
                                                                  doc_type="postmortem", version="1")]))
    assert len(rows) == 2


def test_missing_register_table_says_run_load_data():
    with pytest.raises(SystemExit, match="scripts.load_data"):
        ingest_docs.read_register(FakeBigQuery(missing=True))


def test_empty_register_fails():
    with pytest.raises(SystemExit, match="empty"):
        ingest_docs.read_register(FakeBigQuery([]))


def test_bad_register_rows_fail_before_parsing():
    with pytest.raises(SystemExit, match="status 'draft'"):
        ingest_docs.read_register(FakeBigQuery([_row(status="draft")]))
    with pytest.raises(SystemExit, match="missing file_path"):
        ingest_docs.read_register(FakeBigQuery([_row(file_path="")]))
    with pytest.raises(SystemExit, match="duplicate"):
        ingest_docs.read_register(FakeBigQuery([_row(), _row()]))


def test_dry_run_makes_no_cloud_calls():
    result = subprocess.run([sys.executable, "-m", "scripts.ingest_docs", "--dry-run"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "nothing was sent to the cloud" in result.stdout


# -----------------------------------------------------------------------------
# Steps 3-7 with fakes: bucket, processor, quality gate, rows
# -----------------------------------------------------------------------------

import base64
import hashlib

from google.api_core.exceptions import NotFound


def _md5_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.md5(data).digest()).decode()


class FakeBlob:
    def __init__(self, name, size=1000, content_type="application/pdf"):
        self.name, self.size, self.content_type = name, size, content_type
        self.md5_hash, self.generation = _md5_b64(name.encode()), 1700000000000000


class FakeStorage:
    def __init__(self, names, **overrides):
        self.blobs = [FakeBlob(n, **overrides.get(n, {})) for n in names]

    def list_blobs(self, bucket, prefix):
        return [b for b in self.blobs if b.name.startswith(prefix)]


def _names(register):
    return [ingest_docs.object_name(r) for r in register]


def test_bucket_check_returns_md5_and_skips_unregistered():
    register = [_row(), _row(doc_id="PM-2025-052", version="1", file_path="postmortems/pm-2025-052.pdf",
                             media="pdf_scan", doc_type="postmortem")]
    gcs = FakeStorage(_names(register) + [f"{config.GCS_DOCS_PREFIX}/runbooks/draft-notes.pdf"])
    sources = ingest_docs.check_bucket(gcs, register)
    assert set(sources) == {("RB-CAR-003", "4"), ("PM-2025-052", "1")}
    src = sources[("RB-CAR-003", "4")]
    assert src["uri"].startswith(f"gs://{config.GCS_BUCKET}/") and len(src["md5"]) == 32


def test_bucket_check_fails_on_missing_empty_or_wrong_type():
    register = [_row()]
    with pytest.raises(SystemExit, match="not in the bucket"):
        ingest_docs.check_bucket(FakeStorage([]), register)
    name = _names(register)[0]
    with pytest.raises(SystemExit, match="empty"):
        ingest_docs.check_bucket(FakeStorage([name], **{name: {"size": 0}}), register)
    with pytest.raises(SystemExit, match="content type"):
        ingest_docs.check_bucket(FakeStorage([name], **{name: {"content_type": "text/markdown"}}), register)


class FakeDocAI:
    """Enough of DocumentProcessorServiceClient for ensure_processor()."""

    def __init__(self, existing=(), versions=(config.DOCUMENT_AI_PROCESSOR_VERSION,)):
        from google.cloud import documentai
        self.documentai = documentai
        self.processors = {p: self._proc(p) for p in existing}
        self.versions, self.created = set(versions), []

    def _proc(self, pid, name=None):
        return self.documentai.Processor(name=f"projects/p/locations/us/processors/{pid}",
                                         display_name=name or config.DOCUMENT_AI_PROCESSOR_NAME,
                                         type_="LAYOUT_PARSER_PROCESSOR", state=self.documentai.Processor.State.ENABLED)

    def common_location_path(self, project, location):
        return f"projects/{project}/locations/{location}"

    def processor_path(self, project, location, pid):
        return f"projects/{project}/locations/{location}/processors/{pid}"

    def processor_version_path(self, project, location, pid, version):
        return f"projects/{project}/locations/{location}/processors/{pid}/processorVersions/{version}"

    def get_processor(self, name):
        pid = name.rsplit("/", 1)[-1]
        if pid not in self.processors:
            raise NotFound("gone")
        return self.processors[pid]

    def list_processors(self, parent):
        return list(self.processors.values())

    def create_processor(self, parent, processor):
        self.created.append(processor.display_name)
        self.processors["new1"] = self._proc("new1")
        return self.processors["new1"]

    def get_processor_version(self, name):
        if name.rsplit("/", 1)[-1] not in self.versions:
            raise NotFound("retired")

    def list_processor_versions(self, parent):
        return [SimpleNamespace(name=f"{parent}/processorVersions/{v}") for v in sorted(self.versions)]


@pytest.fixture()
def id_file(tmp_path, monkeypatch):
    path = tmp_path / "processor_id"
    monkeypatch.setattr(config, "DOCUMENT_AI_PROCESSOR_ID_FILE", path)
    return path


def test_processor_reused_from_a_valid_saved_id(id_file):
    id_file.write_text("abc")
    client = FakeDocAI(existing=["abc"])
    assert ingest_docs.ensure_processor(client).endswith(f"/abc/processorVersions/{config.DOCUMENT_AI_PROCESSOR_VERSION}")
    assert client.created == []


def test_stale_saved_id_falls_back_to_find_by_name(id_file):
    id_file.write_text("deleted-one")
    client = FakeDocAI(existing=["real"])
    ingest_docs.ensure_processor(client)
    assert id_file.read_text() == "real" and client.created == []


def test_processor_created_once_when_none_exists(id_file):
    client = FakeDocAI()
    ingest_docs.ensure_processor(client)
    assert client.created == [config.DOCUMENT_AI_PROCESSOR_NAME] and id_file.read_text() == "new1"


def test_retired_parser_version_fails_with_the_offered_ones(id_file):
    client = FakeDocAI(existing=["abc"], versions=("pretrained-layout-parser-v2.0-2026-09-01",))
    with pytest.raises(SystemExit, match="pretrained-layout-parser-v2.0-2026-09-01"):
        ingest_docs.ensure_processor(client)


def _parsed(*chunks):
    return {"chunkedDocument": {"chunks": [{"content": c, "pageSpan": {"pageStart": 1, "pageEnd": 1}} for c in chunks]}}


def test_quality_gate_catches_a_blank_scan():
    register = [_row(), _row(doc_id="PM-2025-052", version="1", media="pdf_scan", doc_type="postmortem")]
    good = _parsed("# Carrier delay (RB-CAR-003 v4)\n\n## Checks\n" + "Read all carrier events. " * 20)
    with pytest.raises(SystemExit, match="PM-2025-052 v1: no chunks"):
        ingest_docs.quality_gate(register, {("RB-CAR-003", "4"): good, ("PM-2025-052", "1"): _parsed()})
    wrong = _parsed("# Something else\n" + "words " * 100)
    with pytest.raises(SystemExit, match="OCR may have failed"):
        ingest_docs.quality_gate(register, {("RB-CAR-003", "4"): good, ("PM-2025-052", "1"): wrong})


def test_rows_take_labels_from_the_register_and_sections_from_headings():
    reg = _row(exception_type="carrier_delay", owner="Logistics Operations")
    sources = {("RB-CAR-003", "4"): {"uri": "gs://b/docs/x.pdf", "md5": "ab" * 16, "generation": 1}}
    parsed = {("RB-CAR-003", "4"): _parsed(
        "# Carrier delay (RB-CAR-003 v4)\n## Checks\n1. Read all carrier events.",
        "__START_OF_ANNOTATION__a picture__END_OF_ANNOTATION__", "   ")}
    rows = ingest_docs.build_rows([reg], sources, parsed, 512, 768)
    assert len(rows) == 1                                           # annotation-only and blank chunks dropped
    row = rows[0]
    assert row["chunk_id"] == "RB-CAR-003@v4#c000" and row["section"] == "Carrier delay (RB-CAR-003 v4) > Checks"
    assert row["status"] == "current" and row["owner"] == "Logistics Operations"
    assert row["effective_date"] == "2026-02-15" and row["source_md5"] == "ab" * 16
    assert row["embedding_dimension"] == 768 and len(row["index_version"]) == 12
    names = {name for name, *_ in ingest_docs.CHUNKS_SCHEMA}
    assert set(row) <= names


def test_index_version_changes_when_a_document_changes():
    register = [_row()]
    a = ingest_docs.index_version(register, {("RB-CAR-003", "4"): {"md5": "1" * 32}}, 512, 768)
    b = ingest_docs.index_version(register, {("RB-CAR-003", "4"): {"md5": "2" * 32}}, 512, 768)
    c = ingest_docs.index_version(register, {("RB-CAR-003", "4"): {"md5": "1" * 32}}, 256, 768)
    assert len({a, b, c}) == 3


def test_a_whole_document_chunk_is_split_into_one_row_per_section():
    """Layout Parser packs a short runbook into one chunk; we cut it at the ## headings (Gate 2)."""
    reg = _row()
    sources = {("RB-CAR-003", "4"): {"uri": "gs://b/docs/x.pdf", "md5": "ab" * 16, "generation": 1}}
    whole = ("# Carrier delay (RB-CAR-003 v4)\n\n## Symptoms\n\n* Order is late.\n\n"
             "## Checks\n\n* Read the carrier events.\n\n## Escalation\n\n* Tell Customer Care.")
    rows = ingest_docs.build_rows([reg], sources, {("RB-CAR-003", "4"): _parsed(whole)}, 512, 768)
    assert [r["section"] for r in rows] == ["Carrier delay (RB-CAR-003 v4) > Symptoms",
                                            "Carrier delay (RB-CAR-003 v4) > Checks",
                                            "Carrier delay (RB-CAR-003 v4) > Escalation"]
    assert all(r["content"].startswith("# Carrier delay (RB-CAR-003 v4)") for r in rows)   # each reads on its own
    assert {r["doc_key"] for r in rows} == {"RB-CAR-003@v4"}
    kept = ingest_docs.build_rows([reg], sources, {("RB-CAR-003", "4"): _parsed(whole)}, 512, 768, section_split=False)
    assert len(kept) == 1 and kept[0]["index_version"] != rows[0]["index_version"]
