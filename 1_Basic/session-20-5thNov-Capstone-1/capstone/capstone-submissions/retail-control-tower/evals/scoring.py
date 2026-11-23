"""Scoring for the Gate 13 evaluation: deterministic first, a model judge only where it must be.

Pure functions on one scored turn (answer text + harness trace rows), so the
scoring itself is tested offline (tests/test_eval_scoring.py), like session 8
eval_scoring.py.

Deterministic checks (always):
- outcome, cause, fulfilable: from the answer's fixed header lines;
- retrieval: expected documents in the top N retrieved (hit@N), and forbidden
  documents (e.g. RB-ALLOC-002@v2) never retrieved or cited;
- trajectory: the expected steps happened, forbidden steps didn't;
- citations: every evidence ID in the answer was returned by a tool;
- facts: the IDs, codes and numbers inside each must_mention phrase appear in
  the answer (e.g. "7 available" needs a 7; "held since T-20h" needs a 20).

Judge (only with --judge): must_mention phrases with no ID or number in them
("re-route needs approval"), and every must_not_claim phrase, because "did the
answer CLAIM X" can't be decided by matching words: an answer may name
CHG-2305 precisely to rule it out.
"""

from __future__ import annotations

import re
from statistics import median

from orchestrator.runtime import parse_header

# Placeholder step labels in golden_questions.jsonl -> our tool names.
TOOL_STEPS = {
    "get_order": "order_lookup",
    "check_fulfilment": "fulfilment_specialist",
    "get_carrier_events": "carrier_events",
    "get_warehouse_events": "warehouse_events",
    "get_recent_changes": "change_log",
    "compare_before_after_change": "change_log",
    "search_knowledge": "knowledge_search",
}
TOP_N_HIT = 5
CODE = re.compile(r"\b(?:[A-Z]{2,}[-_][A-Z0-9]+(?:[-_][A-Z0-9]+)*|ORD-\d{5})\b")
NUMBER = re.compile(r"(?<![\w-])\d+(?:\.\d+)?(?![\w-])")
RELATIVE = re.compile(r"T\s*[-+]\s*(\d+)\s*h", re.I)
DOC_REF = re.compile(r"\b((?:RB-[A-Z]+-\d{3})|(?:PM-\d{4}-\d{3}))(?:\s*(?:@|\s)v(\d+))?")


def steps_of(traces: list[dict]) -> list[str]:
    steps = []
    for trace in traces:
        for tool in trace.get("tools", []):
            step = TOOL_STEPS.get(tool.get("tool"))
            if step and not str(tool.get("outcome", "")).startswith(("blocked", "refused")):
                steps.append(step)
    return steps


def retrieved_docs(traces: list[dict]) -> list[str]:
    docs = []
    for trace in traces:
        for detail in trace.get("details", []):
            docs.extend(detail.get("docs", [])[:TOP_N_HIT])
    return list(dict.fromkeys(docs))


def cited_docs(answer: str) -> list[str]:
    return list(dict.fromkeys(f"{d}@v{v}" if v else d for d, v in DOC_REF.findall(answer or "")))


def doc_match(spec: str, docs: list[str]) -> bool:
    """'RB-ALLOC-002@v3' needs that version; 'RB-INV-001' matches any version."""
    if "@" in spec:
        return spec in docs
    return any(d.split("@")[0] == spec for d in docs)


def fact_tokens(phrase: str) -> list[str]:
    """IDs, codes and numbers a phrase can't be true without. Empty = needs the judge."""
    tokens = [m for m in CODE.findall(phrase)]
    stripped = CODE.sub(" ", RELATIVE.sub(" ", phrase))
    tokens += [n for n in NUMBER.findall(stripped)]
    tokens += RELATIVE.findall(phrase)          # "T-20h" -> "20" (the answer says "20 hours ago")
    return list(dict.fromkeys(tokens))


def fact_present(token: str, answer: str) -> bool:
    if token.isdigit():
        return re.search(rf"(?<![\d.]){re.escape(token)}(?![\d])", answer) is not None
    return token.lower() in answer.lower()


def score_case(case: dict, answer: str, traces: list[dict], judge: dict | None = None) -> dict:
    header = parse_header(answer)
    checks: dict[str, bool | None] = {}

    checks["outcome"] = header["outcome"] == case["expected_outcome"]
    checks["fulfilable"] = (header["fulfilable"] == case["fulfilable"]) if case.get("fulfilable") else None
    checks["cause"] = (header["cause"] == case["expected_cause"]) if case.get("expected_cause") else None

    retrieved, cited = retrieved_docs(traces), cited_docs(answer)
    expected = case.get("expected_docs") or []
    checks["docs_hit"] = all(doc_match(d, retrieved) for d in expected) if expected else None
    forbidden = case.get("forbidden_docs") or []
    checks["no_forbidden_docs"] = (not any(doc_match(d, retrieved + cited) for d in forbidden)) if forbidden else None

    steps = steps_of(traces)
    checks["steps_expected"] = all(s in steps for s in case.get("expected_steps") or []) \
        if case.get("expected_steps") else None
    checks["steps_forbidden"] = (not any(s in steps for s in case["forbidden_steps"])) \
        if case.get("forbidden_steps") else None

    invalid = [i for t in traces for i in t.get("invalid_citations", [])]
    checks["citations_valid"] = not invalid

    facts, needs_judge = [], []
    for phrase in case.get("must_mention") or []:
        tokens = fact_tokens(phrase)
        if tokens:
            missing = [t for t in tokens if not fact_present(t, answer)]
            facts.append({"phrase": phrase, "ok": not missing, "missing": missing})
        else:
            needs_judge.append(phrase)
    checks["facts"] = all(f["ok"] for f in facts) if facts else None

    if judge is not None:
        checks["judge_mentions"] = judge.get("mentions_ok")
        checks["judge_no_false_claims"] = judge.get("claims_ok")

    scored = {k: v for k, v in checks.items() if v is not None}
    first_failure = next((k for k, v in scored.items() if v is False), None)
    return {
        "id": case["id"], "category": case["category"], "scenario": case.get("scenario"),
        "passed": all(scored.values()), "first_failure": first_failure, "checks": checks,
        "header": header, "steps": steps, "retrieved_docs": retrieved, "cited_docs": cited,
        "facts": facts, "phrases_for_judge": needs_judge, "judge": judge, "invalid_citations": invalid,
        "latency_s": round(sum(t.get("latency_s", 0) for t in traces), 2),
        "model_calls": sum(t.get("model_calls", 0) for t in traces),
        "tool_calls": sum(t.get("tool_calls", 0) for t in traces),
        "tokens_in": sum(t.get("tokens", {}).get("in", 0) for t in traces),
        "tokens_out": sum(t.get("tokens", {}).get("out", 0) for t in traces),
        "termination": [t.get("termination") for t in traces],
    }


def _rate(values: list[bool | None]) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def aggregate(scored: list[dict]) -> dict:
    ran = [s for s in scored if not s.get("skipped")]
    checks = sorted({k for s in ran for k in s["checks"]})
    by_category = {}
    for cat in sorted({s["category"] for s in ran}):
        items = [s for s in ran if s["category"] == cat]
        by_category[cat] = {"cases": len(items), "passed": sum(s["passed"] for s in items)}
    latencies = [s["latency_s"] for s in ran if s["latency_s"]]
    return {
        "cases": len(scored), "ran": len(ran), "skipped": len(scored) - len(ran),
        "passed": sum(s["passed"] for s in ran),
        "pass_rate": round(sum(s["passed"] for s in ran) / len(ran), 3) if ran else None,
        "checks": {k: _rate([s["checks"].get(k) for s in ran]) for k in checks},
        "by_category": by_category,
        "latency_s": {"p50": median(latencies) if latencies else None, "p95": _p95(latencies)},
        "avg_model_calls": round(sum(s["model_calls"] for s in ran) / len(ran), 2) if ran else None,
        "avg_tool_calls": round(sum(s["tool_calls"] for s in ran) / len(ran), 2) if ran else None,
        "avg_tokens_in": round(sum(s.get("tokens_in", 0) for s in ran) / len(ran)) if ran else None,
        "avg_tokens_out": round(sum(s.get("tokens_out", 0) for s in ran) / len(ran)) if ran else None,
    }
