"""Offline tests for the search runtime: no Google Cloud call, no cost, no 429s.

They replay responses recorded once from the real services
(tests/fixtures/runtime/, made with MEDEVIDENCE_RECORD=1) and check the code
around them: hard filters, authority roles, exact-ID routing, not-found and
insufficient paths, citation check and Sources links.

The runtime refuses to create any Google client in offline mode, so these
tests also prove that nothing reached the cloud.

Run from submission/:  pytest tests/
Re-record after changing the corpus, filters or prompts:
    MEDEVIDENCE_RECORD=1 python tests/record_runtime_fixtures.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["MEDEVIDENCE_OFFLINE"] = "1"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "tredence-fde-1")
os.environ.setdefault("GCS_BUCKET", "tredence-fde-1-medevidence-vks")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import rag_runtime as rt  # noqa: E402  (environment must be set before import)


def _docs(chunks):
    return {c["document_id"] for c in chunks}


def test_current_germany_uses_only_current_german_evidence():
    r = rt.answer("Current AX-17 renal guidance in Germany?", mode="current", country="Germany")
    assert r["outcome"] == "answered"
    # Hard filters: the US label and the superseded v3.8 never reach the search.
    assert not _docs(r["candidates"]) & {"US-AX17-PI-050", "DE-AX17-LBL-038", "DE-AX17-HSL-2019-2021"}
    # Table 3 is in the evidence, its card is local guidance, and the link opens page 6.
    table3 = [c for c in r["cards"] if c["chunk"]["table_id"] == "Table 3"]
    assert table3 and table3[0]["role"] == "LOCAL GUIDANCE"
    assert r["citation_check"] == "pass"
    assert "#page=6" in r["sources"]
    assert "25 mg" in r["answer"]


def test_historical_germany_labels_v38_as_historical():
    r = rt.answer("German AX-17 guidance before latest revision?", mode="historical", country="Germany")
    assert r["outcome"] == "answered"
    v38 = [c for c in r["cards"] if c["chunk"]["document_id"] == "DE-AX17-LBL-038"]
    assert v38 and all(c["role"].startswith("HISTORICAL") for c in v38)
    assert "50 mg" in r["answer"]


def test_exact_id_restricts_to_that_document():
    r = rt.answer("What does SB-AX17-2026-09 require?", mode="current", country="Germany")
    assert r["filters"]["document_ids"] == ["SB-AX17-2026-09"]
    assert _docs(r["candidates"]) == {"SB-AX17-2026-09"}
    assert "Day 14" in r["answer"] and r["citation_check"] == "pass"


def test_unknown_country_is_not_found_without_search():
    r = rt.answer("Approved AX-17 dosage in Japan?", mode="current", country="Japan")
    assert r["outcome"] == "not_found"
    assert r["candidates"] == [] and "Japan" in r["answer"]


def test_missing_key_term_is_insufficient_without_gemini():
    r = rt.answer("Does AX-17 interact with warfarin?", mode="current", country="Germany")
    assert r["outcome"] == "insufficient"
    assert any("warfarin" in reason for reason in r["reasons"])
    assert "generate" not in r["latency_ms"]  # Gemini was never called


def test_unknown_document_id_is_not_found():
    r = rt.answer("What does HN-SAF-017 say?", mode="current", country="Germany")
    assert r["outcome"] == "not_found" and "HN-SAF-017" in r["answer"]


def test_citation_check_blocks_invented_evidence_ids():
    cards = [{"id": "E1"}, {"id": "E2"}]
    ok, why = rt.check_citations({"verdict": "answered", "answer": "25 mg [E1] and 75 mg [E9]", "citations": ["E1"]}, cards)
    assert not ok and "E9" in why
    ok, _ = rt.check_citations({"verdict": "answered", "answer": "no citation at all", "citations": []}, cards)
    assert not ok


def test_offline_mode_never_creates_a_cloud_client():
    import pytest
    with pytest.raises(RuntimeError, match="Offline mode"):
        rt._bq()


def test_table_values_stay_in_their_column():
    """Regression (Step 4, D30 reversed): Table 3's Severe row has starting dose
    "Specialist review" and maximum "25 mg/day". With thinking off, the answer
    writer twice reported 25 mg/day as the severe STARTING dose, and every check
    passed (the citation was valid and the number exists in the cited card)."""
    r = rt.answer("What is the current renal starting dose of AX-17?", mode="current", country="Germany")
    assert r["outcome"] == "answered" and r["citation_check"] == "pass"
    severe = [line for line in r["answer"].replace(". ", ".\n").splitlines() if "evere" in line]
    assert severe and "specialist review" in " ".join(severe).lower()
    assert not any("starting dose" in line.lower() and "25 mg/day" in line for line in severe)
