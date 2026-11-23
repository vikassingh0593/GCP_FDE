"""data/docs: the PDFs Document AI will parse, and the register that describes them."""

from __future__ import annotations

import csv

from pypdf import PdfReader

from common import config


def _register() -> list[dict]:
    with config.DOCUMENT_REGISTER_FILE.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _text(path) -> str:
    return "".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def test_text_pdfs_have_a_text_layer_with_their_id():
    for row in _register():
        if row["media"] == "pdf_text":
            assert row["doc_id"] in _text(config.DOCS_DIR / row["file_path"]), row["doc_id"]


def test_scanned_pdf_has_no_text_layer_so_ocr_is_required():
    scans = [r for r in _register() if r["media"] == "pdf_scan"]
    assert len(scans) == 1
    assert not _text(config.DOCS_DIR / scans[0]["file_path"]).strip()


def test_every_markdown_source_has_a_register_row():
    sources = {p.relative_to(config.DATA_DIR / "docs_source").with_suffix(".pdf").as_posix()
               for p in (config.DATA_DIR / "docs_source").rglob("*.md")}
    assert sources == {r["file_path"] for r in _register()}


def test_no_customer_details_in_any_document():
    names = {"Ananya Rao", "Annapurna Caterers", "Harish Gowda", "+91 98000"}
    for row in _register():
        if row["media"] == "pdf_text":
            text = _text(config.DOCS_DIR / row["file_path"])
            assert not any(n in text for n in names), row["doc_id"]


def test_superseded_version_is_marked_and_points_to_its_replacement():
    rows = {(r["doc_id"], r["version"]): r for r in _register()}
    old, new = rows[("RB-ALLOC-002", "2")], rows[("RB-ALLOC-002", "3")]
    assert old["status"] == "superseded" and old["superseded_by"] == "RB-ALLOC-002 v3"
    assert new["status"] == "current"
