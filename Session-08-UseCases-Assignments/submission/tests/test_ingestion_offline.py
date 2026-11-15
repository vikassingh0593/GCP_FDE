"""Offline tests for ingestion rules (no cloud call): template tagging (D72) and table facts (D74).

They rebuild the pieces exactly as src/03_embed_and_load.py does, from the files the pipeline left on disk
(output/chunks_cs512.json, the quality-gate reports and the cached Layout Parser results).

Run from submission/:  pytest tests/
"""

from __future__ import annotations

import copy
import importlib
import os
import sys
from functools import lru_cache
from pathlib import Path

os.environ["MEDEVIDENCE_OFFLINE"] = "1"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "tredence-fde-1")
os.environ.setdefault("GCS_BUCKET", "tredence-fde-1-medevidence-vks")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

emb = importlib.import_module("03_embed_and_load")


@lru_cache(maxsize=1)
def _pieces() -> list[dict]:
    """Steps a–e of 03_embed_and_load.main(): split, tag templates, collapse copies (no document card)."""
    chunks, quarantine, _, _ = emb.load_inputs()
    pieces, pages = [], {}
    for c in chunks:
        if c["filename"] in quarantine:
            continue
        pages.setdefault(c["filename"], emb.table_pages(c["filename"]))
        for p in emb.split_chunk(c, pages[c["filename"]])[0]:
            p.update(document_id=c["document_id"], filename=c["filename"])
            pieces.append(p)
    emb.tag_templates(pieces)
    return emb.collapse_copies(pieces)[0]


def test_template_rule_keeps_a_dose_schedule_written_as_sentences_searchable():
    """D72: a list in one place repeats its sentence shape inside ONE piece; filler is scattered across many.
    Counting repeats (the old rule) hid a 6-step schedule; counting pieces keeps it and still catches the filler."""
    schedule = {"block_type": "text", "chunk_id": "TEST-schedule", "document_id": "TEST", "content": "## Titration\n\n"
                + " ".join(f"On day {d}, give {mg} mg once daily." for d, mg in
                           [(1, 25), (8, 50), (15, 75), (22, 100), (29, 125), (36, 150)])}
    pieces = copy.deepcopy(_pieces()) + [schedule]
    emb.tag_templates(pieces)
    assert not pieces[-1]["boilerplate"]
    assert sum(not p["boilerplate"] for p in pieces[:-1]) == 22  # + the scanned letters' card = 23 searchable


def test_table_facts_link_every_table_and_keep_each_cell():
    """D74: one fact per cell, read from the parser's structured tables and linked to the table piece."""
    pieces = _pieces()
    facts = emb.table_facts(pieces)
    tables = {p["chunk_id"] for p in pieces if p["block_type"] == "table"}
    assert len(tables) == 10 and tables == {f["chunk_id"] for f in facts}

    def cell(doc: str, row: str, column: str) -> str:
        return next(f["value"] for f in facts
                    if f["document_id"] == doc and f["row_label"] == row and f["column_label"] == column)

    assert cell("DE-AX17-LBL-042", "Moderate", "Starting dose") == "25 mg OD"
    assert cell("DE-AX17-LBL-042", "Moderate", "Maximum") == "50 mg/day"
    assert cell("DE-AX17-LBL-038", "Moderate", "Historical starting dose") == "50 mg OD"  # no header row in its parse
    assert cell("HN-204", "Rash", "AX-17 %") == "17.8"
