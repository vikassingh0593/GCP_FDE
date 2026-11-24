"""evals/scoring.py: the deterministic checks, scored on hand-made answers and traces."""

from __future__ import annotations

from evals.scoring import aggregate, cited_docs, doc_match, fact_tokens, score_case

CASE = {"id": "A02", "category": "answerable", "scenario": "S2", "expected_outcome": "cause_named",
        "expected_cause": "allocation_reserved", "fulfilable": "no",
        "must_mention": ["50 on hand", "45 reserved", "ORD-78431", "held since T-20h", "re-route needs approval"],
        "must_not_claim": ["shortage"], "expected_docs": ["RB-ALLOC-002@v3"], "forbidden_docs": ["RB-ALLOC-002@v2"],
        "expected_steps": ["order_lookup", "fulfilment_specialist", "knowledge_search"], "forbidden_steps": []}

ANSWER = """OUTCOME: cause_named
CAUSE: allocation_reserved
FULFILABLE: no
ANSWER: 50 on hand, 45 reserved by ORD-78431 for 20 hours.
SOURCES: RB-ALLOC-002 v3"""

TRACE = {"tools": [{"tool": "get_order", "outcome": "ok"}, {"tool": "check_fulfilment", "outcome": "ok"},
                   {"tool": "search_knowledge", "outcome": "ok"}],
         "details": [{"strategy": "hybrid", "docs": ["RB-ALLOC-002@v3", "PM-2026-009@v1"]}],
         "invalid_citations": [], "latency_s": 9.5, "model_calls": 4, "tool_calls": 3, "termination": "NORMAL"}


def test_fact_tokens():
    assert fact_tokens("50 on hand") == ["50"]
    assert fact_tokens("WH-DEL-01 has 55 available") == ["WH-DEL-01", "55"]
    assert fact_tokens("held since T-20h") == ["20"]
    assert fact_tokens("re-route needs approval") == []            # left for the judge


def test_doc_matching_respects_versions():
    assert doc_match("RB-ALLOC-002@v3", ["RB-ALLOC-002@v3"]) and not doc_match("RB-ALLOC-002@v2", ["RB-ALLOC-002@v3"])
    assert doc_match("RB-INV-001", ["RB-INV-001@v2"])
    assert cited_docs("SOURCES: RB-ALLOC-002 v3, PM-2026-009") == ["RB-ALLOC-002@v3", "PM-2026-009"]


def test_a_good_answer_passes():
    result = score_case(CASE, ANSWER, [TRACE])
    assert result["passed"], result
    assert result["phrases_for_judge"] == ["re-route needs approval"]


def test_failures_name_the_first_broken_stage():
    wrong_version = {**TRACE, "details": [{"strategy": "hybrid", "docs": ["RB-ALLOC-002@v2"]}]}
    result = score_case(CASE, ANSWER, [wrong_version])
    assert not result["passed"] and result["checks"]["docs_hit"] is False
    assert result["checks"]["no_forbidden_docs"] is False

    no_specialist = {**TRACE, "tools": TRACE["tools"][:1] + TRACE["tools"][2:]}
    assert score_case(CASE, ANSWER, [no_specialist])["checks"]["steps_expected"] is False

    invented = {**TRACE, "invalid_citations": ["EV-INV-x-abcdef"]}
    assert score_case(CASE, ANSWER, [invented])["checks"]["citations_valid"] is False

    missing_number = ANSWER.replace("45 reserved", "most reserved")
    assert score_case(CASE, missing_number, [TRACE])["checks"]["facts"] is False


def test_aggregate():
    good, bad = score_case(CASE, ANSWER, [TRACE]), score_case(CASE, "OUTCOME: check_next", [TRACE])
    metrics = aggregate([good, bad, {"id": "C02", "category": "stale_cache", "skipped": True}])
    assert metrics["ran"] == 2 and metrics["passed"] == 1 and metrics["skipped"] == 1
    assert metrics["checks"]["outcome"] == 0.5


def test_numbers_written_as_words_count():
    from evals.scoring import fact_present
    assert fact_present("9", "the sync job failed silently for nine hours")
    assert not fact_present("9", "the sync job failed for many hours")


def test_gate_fails_on_any_safety_check_below_one():
    from evals.run_evals import gate
    ok = {"checks": {"citations_valid": 1.0, "outcome": 0.9, "judge_mentions": None}}
    assert gate(ok) == []
    assert gate({"checks": {"citations_valid": 0.97, "outcome": 0.9}}) == ["citations_valid 0.97 < 1.0"]
