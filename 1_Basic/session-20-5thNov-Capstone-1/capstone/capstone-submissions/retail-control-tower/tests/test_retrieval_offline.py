"""orchestrator/retrieval: query terms, RRF fusion, abstention, and cache keys that change with the register."""

from __future__ import annotations

import pytest

from orchestrator.retrieval import search as s


def chunk(cid, doc="RB-CAR-003", version="4", doc_type="runbook"):
    return {"chunk_id": cid, "doc_id": doc, "version": version, "doc_type": doc_type, "title": "t", "section": "S",
            "content": f"text of {cid}", "exception_type": None, "warehouse_id": None, "page_start": 1, "page_end": 1,
            "incident_date": None, "effective_date": None, "media": "pdf_text"}


def test_exact_codes_and_key_words():
    assert s.exact_codes("What does ALLOC-E107 mean vs WX-HOLD at WH-BLR-01?") == ["ALLOC-E107", "WX-HOLD", "WH-BLR-01"]
    assert s.exact_codes("is SYSTEM_DOWN open?") == ["SYSTEM_DOWN"]
    words = s.key_words("Stock is sitting on the shelf but it's held for other customers' orders")
    assert "shelf" in words and "held" in words and "that" not in words


def test_rrf_rewards_agreement_between_legs():
    dense = [chunk("a"), chunk("b"), chunk("c")]
    lexical = [chunk("c"), chunk("d")]
    fused = s.rrf_fuse(dense, lexical)
    assert fused[0]["chunk_id"] == "c"                       # in both lists beats first in one
    assert fused[0]["legs"] == ["dense#3", "lexical#1"]
    assert {r["chunk_id"] for r in fused} == {"a", "b", "c", "d"}


@pytest.fixture()
def wired(monkeypatch):
    state = {"fingerprint": "fp1", "rerank_scores": {"a": 0.9, "b": 0.1}, "calls": 0}
    monkeypatch.setattr(s, "knowledge_version", lambda table, dim: {"index_version": "iv1",
                                                                    "register_fingerprint": state["fingerprint"],
                                                                    "current_docs": ["RB-CAR-003@v4"]})
    monkeypatch.setattr(s, "embed_query", lambda q, dimension=None: ([0.1] * 3, False))

    def dense(*a, **k):
        state["calls"] += 1
        return [chunk("a"), chunk("b", "PM-2026-009", "1", "postmortem")]
    monkeypatch.setattr(s, "dense_search", dense)
    monkeypatch.setattr(s, "lexical_search", lambda *a, **k: [])
    monkeypatch.setattr(s, "rerank", lambda q, c, n: [dict(x, relevance=state["rerank_scores"][x["chunk_id"]]) for x in c])
    s._retrieval_cache.clear()
    return state


def test_low_relevance_is_dropped_and_postmortems_are_labelled_hints(wired):
    wired["rerank_scores"] = {"a": 0.9, "b": 0.5}
    out = s.search("weather hold at a hub")
    cards = out["data"]["results"]
    assert [c["doc_id"] for c in cards] == ["RB-CAR-003", "PM-2026-009"]
    assert cards[1]["role"].startswith("historical hint")
    assert cards[0]["evidence_id"].startswith("EV-DOC-a-")


def test_nothing_relevant_means_abstain(wired):
    wired["rerank_scores"] = {"a": 0.05, "b": 0.01}
    out = s.search("what is the weather in Paris")
    assert out["status"] == "no_evidence" and "do not answer from general knowledge" in out["message"]


def test_cache_hit_and_register_change_invalidates(wired):
    s.search("weather hold at a hub")
    second = s.search("weather hold at a hub")
    assert second["_trace"]["cache"] == "hit" and wired["calls"] == 1
    wired["fingerprint"] = "fp2"                              # a runbook was superseded or withdrawn
    third = s.search("weather hold at a hub")
    assert third["_trace"]["cache"] == "miss" and wired["calls"] == 2


def test_bad_filters_are_rejected_before_any_query():
    assert s.search("x y z", doc_type="manual")["error_type"] == "invalid_argument"
    assert s.search("x y z", legs="both")["error_type"] == "invalid_argument"
