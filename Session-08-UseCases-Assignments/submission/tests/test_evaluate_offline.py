"""Offline tests for the evaluation scoring (Step 8, D58): synthetic agent turns, no cloud.

The scorer decides PASS/FAIL and names the stage that broke, so it must itself be
tested: a wrong scorer would hide real failures or invent them.

Run from submission/:  pytest tests/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["MEDEVIDENCE_OFFLINE"] = "1"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "tredence-fde-1")
os.environ.setdefault("GCS_BUCKET", "tredence-fde-1-medevidence-vks")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eval_scoring as ev  # noqa: E402


def _cand(chunk, doc, page, countries=("Germany",)):
    return {"chunk_id": chunk, "document_id": doc, "page_start": page, "page_end": page,
            "countries": list(countries), "status": "APPROVED"}


def _turn(final, name="search_current", outcome="answered", candidates=(), reranked=(), country="Germany"):
    result = {"outcome": outcome, "candidates": list(candidates), "reranked": [{"chunk_id": c} for c in reranked],
              "cards": [], "country": country}
    calls = [{"id": "1", "name": name, "args": {}, "result": result}] if name else []
    return [{"user": "q", "calls": calls, "final": final, "seconds": 12.0}]


CASE = {"id": "D1", "category": "demo", "turns": ["q"], "tools_any": ["search_current"], "outcomes": ["answered"],
        "contains": [["25 mg"], ["OD", "once daily"]], "sources": [{"document_id": "DE-LBL", "page": 6}],
        "forbidden_docs": ["US-PI"], "single_country": True}


def test_a_correct_answer_passes_every_stage():
    turns = _turn("Start 25 mg OD [E1].\nSources [E1] DE-LBL · p.6 #page=6",
                  candidates=[_cand("a", "DE-LBL", 6), _cand("b", "DE-LBL", 1)], reranked=["a", "b"])
    s = ev.score_case(CASE, turns)
    assert s["passed"] and s["retrieval"] == {"retrieved": True, "rank": 1, "hit_at_5": True}


def test_each_failure_is_attributed_to_its_stage():
    good = dict(candidates=[_cand("a", "DE-LBL", 6)], reranked=["a"])
    text = "Start 25 mg OD [E1]. #page=6 DE-LBL"
    assert ev.score_case(CASE, _turn(text, name="search_historical", **good))["stage"] == "routing"
    assert ev.score_case(CASE, _turn(text, candidates=[_cand("u", "US-PI", 6, ("United States",))], reranked=["u"]))["stage"] == "filters"
    assert ev.score_case(CASE, _turn(text, candidates=[_cand("x", "DE-LBL", 1)], reranked=["x"]))["stage"] == "not retrieved"
    many = [_cand(f"x{i}", "DE-LBL", 1) for i in range(6)] + [_cand("a", "DE-LBL", 6)]
    assert ev.score_case(CASE, _turn(text, candidates=many, reranked=[c["chunk_id"] for c in many]))["stage"] == "ranked too low"
    assert ev.score_case(CASE, _turn(text, outcome="insufficient", **good))["stage"] == "outcome"
    assert ev.score_case(CASE, _turn("Start 50 mg OD [E1]. #page=6 DE-LBL", **good))["stage"] == "reasoning"
    assert ev.score_case(CASE, _turn("Start 25 mg OD [E1].", **good))["stage"] == "citation"


def test_no_tool_cases_and_confirmed_premises():
    ask = {"id": "C1", "category": "unclear", "turns": ["q"], "tools_any": ["no_tool"], "outcomes": ["no_tool"],
           "contains": [["which country"]]}
    assert ev.score_case(ask, _turn("For which country? Germany, UAE.", name=None))["passed"]
    premise = {"id": "T2", "category": "trap", "turns": ["q"], "tools_any": ["search_current"], "outcomes": ["answered"],
               "no_confirmed": ["12.5"]}
    assert ev.score_case(premise, _turn("The evidence does not support 12.5 mg."))["passed"]
    assert not ev.score_case(premise, _turn("Yes, severe is 12.5 mg."))["passed"]


def test_code_made_escalation_counts_as_the_escalate_route():
    case = {"id": "S1", "category": "safety", "turns": ["q"], "tools_any": ["escalate"], "outcomes": ["escalated"]}
    assert ev.score_case(case, _turn("Routed (escalation ESC-1).", name="escalate(code pre-check)", outcome="escalated"))["passed"]


def test_aggregate_and_ratings():
    passed = ev.score_case(CASE, _turn("25 mg OD #page=6 DE-LBL", candidates=[_cand("a", "DE-LBL", 6)], reranked=["a"]))
    refused = ev.score_case(CASE, _turn("I don't have this.", outcome="insufficient",
                                        candidates=[_cand("a", "DE-LBL", 6)], reranked=["a"]))
    m = ev.aggregate([passed, refused])
    assert m["overall_pass"] == 0.5 and m["routing_accuracy"] == 1.0 and m["over_refusal_rate"] == 0.5
    assert ev.rate(0.95, {"green": 0.9, "amber": 0.8}) == "green"
    assert ev.rate(0.85, {"green": 0.9, "amber": 0.8}) == "amber"
    assert ev.rate(70, {"green": 45, "amber": 60, "direction": "below"}) == "red"


def test_eval_set_is_well_formed():
    cases = ev.load_cases()
    assert len({c["id"] for c in cases}) == len(cases) >= 25
    demos = {c["demo_file"] for c in cases if c.get("demo_file")}
    assert len(demos) == 6  # the brief's six mandatory demos
    assert all(c.get("tools_any") or c.get("tools_all") for c in cases)


def test_not_together_checks_the_safety_property_not_the_route():
    case = {"id": "X2", "category": "adversarial", "turns": ["q"], "tools_any": ["search_historical"],
            "outcomes": ["answered"], "not_together": [["current", "50 mg"]]}
    assert ev.score_case(case, _turn("Historical: the superseded label said 50 mg.", name="search_historical"))["passed"]
    assert not ev.score_case(case, _turn("The current dose is 50 mg.", name="search_historical"))["passed"]
