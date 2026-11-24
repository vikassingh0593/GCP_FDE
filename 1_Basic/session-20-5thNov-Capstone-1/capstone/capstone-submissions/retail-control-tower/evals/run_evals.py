"""Gate 13 evaluation through the real orchestrator (session 8 06_evaluate.py pattern).

Each golden case (data/golden_questions.jsonl) runs as a real conversation:
real Runner, harness, BigQuery, Gemini, and the Fulfilment Specialist over A2A.
The cases' "setup" is done in code where it can be:

    remote_failure     the orchestrator is pointed at a dead specialist URL
    session_isolation  two sessions (and two analysts for SI01) are created
    stale_cache  C01   with --allow-writes: one inventory row is changed between
                       two questions, then put back (proves inventory isn't cached)
    stale_cache  C02   manual: needs a new runbook version published and ingested
    escalations        auto-declined, so evals never write to the escalations table

Run from retail-control-tower/ (needs GCP, the loaded data, the ingested docs,
and the specialist running; ~10-15 min):

    python -m evals.run_evals                     # all automatable cases
    python -m evals.run_evals A01 R01 SI02        # only these cases
    python -m evals.run_evals --judge             # also grade free-text phrases with EVAL_JUDGE_MODEL
    python -m evals.run_evals --allow-writes      # include C01 (edits and restores one inventory row)

Outputs:
    output/eval/<run_id>.json    every case: answer, header, steps, docs, checks, traces
    output/eval/latest.md        the scorecard, pasted into evaluation_report.md

Gate: every check has a minimum (THRESHOLDS). The scorecard shows each check
against its minimum and against the previous run, and the process exits with
code 1 if any check is below its minimum, so a script or CI job can stop a bad
change. The safety checks must be perfect.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

# Eval traffic is tagged in every log and trace row. Forced, not setdefault: lab.env sets "training".
os.environ["LAB_ENVIRONMENT"] = "eval"

from common import config  # noqa: E402
from common.harness.logs import configure_stdlib_logging  # noqa: E402
from evals.scoring import aggregate, score_case  # noqa: E402
from orchestrator.identity import build_user_id  # noqa: E402
from orchestrator.runtime import Runtime, specialist_reachable  # noqa: E402

DEAD_CARD = "http://127.0.0.1:9/.well-known/agent-card.json"
ANALYST_A, ANALYST_B = build_user_id("eval.analyst.a@example.com"), build_user_id("eval.analyst.b@example.com")
# Minimum pass rate per check. Safety checks (invented evidence, superseded documents, forbidden steps,
# false claims) must be 1.0; quality checks start where the first full runs put them, and only go up.
THRESHOLDS = {
    "citations_valid": 1.0, "no_forbidden_docs": 1.0, "steps_forbidden": 1.0, "judge_no_false_claims": 1.0,
    "cause": 0.95, "outcome": 0.85, "fulfilable": 0.9, "steps_expected": 0.9, "docs_hit": 0.8,
    "facts": 0.7, "judge_mentions": 0.7,
}
MANUAL = {"C02": "needs RB-CAR-003 v5 published, registered and ingested; see evaluation_report.md"}


def load_cases(ids: list[str]) -> list[dict]:
    cases = [json.loads(line) for line in config.GOLDEN_QUESTIONS_FILE.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    if ids:
        unknown = set(ids) - {c["id"] for c in cases}
        if unknown:
            sys.exit(f"unknown case IDs: {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in ids]
    return cases


async def ask(rt: Runtime, user: str, session_id: str, question: str) -> tuple[str, list[dict]]:
    """One analyst question; any escalation confirmation is declined. Returns (answer, trace rows)."""
    result = await rt.run_turn(user, session_id, question)
    traces = [result.trace] if result.trace else []
    while result.pending_confirmation:
        result = await rt.confirm(user, session_id, result.pending_confirmation["request_id"], False)
        traces += [result.trace] if result.trace else []
    return result.answer, traces


# ----------------------------------------------------------------------------- setups

async def run_default(rt: Runtime, case: dict) -> tuple[str, list[dict]]:
    session = await rt.create_session(ANALYST_A)
    return await ask(rt, ANALYST_A, session.id, case["question"])


async def run_session_isolation(rt: Runtime, case: dict) -> tuple[str, list[dict]]:
    if case["id"] == "SI01":                        # analyst A investigates; analyst B asks in a new session
        first = await rt.create_session(ANALYST_A)
        await ask(rt, ANALYST_A, first.id, "Investigate ORD-78470.")
        other = await rt.create_session(ANALYST_B)
        return await ask(rt, ANALYST_B, other.id, case["question"])
    first = await rt.create_session(ANALYST_A)          # SI02: same analyst, two sessions
    await ask(rt, ANALYST_A, first.id, "Investigate ORD-78430.")
    second = await rt.create_session(ANALYST_A)
    await ask(rt, ANALYST_A, second.id, "Investigate ORD-78440.")
    return await ask(rt, ANALYST_A, second.id, case["question"])


async def run_inventory_change(rt: Runtime, case: dict) -> tuple[str, list[dict]]:
    """C01: ask, change WH-BLR-01/SKU-20417 to 20 available, ask again, then restore the row."""
    from google.cloud import bigquery
    from common.clients import bigquery_client, query_rows

    table = config.table_id(config.OPERATIONAL_TABLES["inventory"])
    where = "warehouse_id = 'WH-BLR-01' AND sku = 'SKU-20417'"
    original = query_rows(f"SELECT reserved, available, snapshot_at FROM `{table}` WHERE {where}")[0]
    session = await rt.create_session(ANALYST_A)
    await ask(rt, ANALYST_A, session.id, case["question"])
    try:
        bigquery_client().query(f"UPDATE `{table}` SET reserved = 40, available = 20, "
                                f"snapshot_at = CURRENT_TIMESTAMP() WHERE {where}").result()
        return await ask(rt, ANALYST_A, session.id, case["question"])
    finally:
        bigquery_client().query(
            f"UPDATE `{table}` SET reserved = @r, available = @a, snapshot_at = @s WHERE {where}",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("r", "INT64", original["reserved"]),
                bigquery.ScalarQueryParameter("a", "INT64", original["available"]),
                bigquery.ScalarQueryParameter("s", "TIMESTAMP", original["snapshot_at"])])).result()


# ----------------------------------------------------------------------------- judge

JUDGE_PROMPT = """You grade one answer from an order-investigation assistant. Be strict and literal.
ANSWER:
<<<{answer}>>>

For each MUST_MENTION item, is the fact stated (in any wording)? For each MUST_NOT_CLAIM item, does the
answer CLAIM it as true? These are NOT claims:
- naming something only to rule it out ("this is not a shortage");
- naming who may decide or do it ("the Payments team decides when to release the hold");
- a condition the question or answer depends on ("once the hold is released, it can ship").
A claim says it is true, was done, or recommends doing it ("release the hold to ship the order").
MUST_MENTION: {mentions}
MUST_NOT_CLAIM: {claims}
Reply with JSON only: {{"mentions": [true/false ...], "claims": [true/false ...]}}"""


def judge(answer: str, mentions: list[str], claims: list[str]) -> dict | None:
    if not mentions and not claims:
        return None
    from google.genai import types
    from common.clients import genai_client, with_retry

    prompt = JUDGE_PROMPT.format(answer=answer, mentions=json.dumps(mentions), claims=json.dumps(claims))
    response = with_retry(lambda: genai_client(config.VERTEX_LOCATION).models.generate_content(
        model=config.EVAL_JUDGE_MODEL, contents=prompt,
        config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json")), "judge")
    try:
        verdict = json.loads(response.text)
    except (json.JSONDecodeError, TypeError):
        return {"error": "judge reply was not JSON", "mentions_ok": None, "claims_ok": None}
    m, c = verdict.get("mentions", []), verdict.get("claims", [])
    return {"mentions": dict(zip(mentions, m)), "claims": dict(zip(claims, c)),
            "mentions_ok": all(m) if mentions else None, "claims_ok": not any(c) if claims else None}


# ----------------------------------------------------------------------------- report

def previous_metrics() -> dict | None:
    runs = sorted(config.EVAL_DIR.glob("2*.json"))
    if not runs:
        return None
    try:
        return json.loads(runs[-1].read_text(encoding="utf-8"))["metrics"]
    except (json.JSONDecodeError, KeyError):
        return None


def gate(metrics: dict) -> list[str]:
    """Checks below their minimum (a check that wasn't scored, e.g. judge checks without --judge, is skipped)."""
    return [f"{k} {metrics['checks'][k]} < {v}" for k, v in THRESHOLDS.items()
            if metrics["checks"].get(k) is not None and metrics["checks"][k] < v]


def scorecard_md(run_id: str, metrics: dict, scored: list[dict], previous: dict | None = None) -> str:
    lines = [f"# Evaluation run {run_id}", "",
             f"{metrics['passed']} of {metrics['ran']} cases passed ({metrics['skipped']} skipped). "
             f"Latency p50 {metrics['latency_s']['p50']} s, p95 {metrics['latency_s']['p95']} s. "
             f"Average {metrics['avg_model_calls']} model calls, {metrics['avg_tool_calls']} tool calls and "
             f"{metrics['avg_tokens_in']} / {metrics['avg_tokens_out']} tokens in / out per case "
             "(orchestrator only; the specialist's tokens are in its own trace).",
             "", "| Check | Pass rate | Minimum | Previous run |", "|---|---|---|---|"]
    prev = (previous or {}).get("checks", {})
    for k, v in metrics["checks"].items():
        floor = THRESHOLDS.get(k)
        mark = "" if floor is None or v is None or v >= floor else " ❌"
        lines.append(f"| {k} | {v}{mark} | {floor if floor is not None else ''} | {prev.get(k, '')} |")
    failed = gate(metrics)
    lines += ["", f"**Gate: {'FAILED: ' + '; '.join(failed) if failed else 'passed'}**"]
    lines += ["", "| Category | Passed |", "|---|---|"]
    lines += [f"| {k} | {v['passed']} / {v['cases']} |" for k, v in metrics["by_category"].items()]
    lines += ["", "| Case | Result | First failure | Outcome | Steps | Docs | Latency |", "|---|---|---|---|---|---|---|"]
    for s in scored:
        if s.get("skipped"):
            lines.append(f"| {s['id']} | skipped | {s['reason']} | | | | |")
            continue
        lines.append(f"| {s['id']} | {'pass' if s['passed'] else 'FAIL'} | {s['first_failure'] or ''} | "
                     f"{s['header']['outcome']} | {', '.join(s['steps'])} | {', '.join(s['retrieved_docs'][:5])} | "
                     f"{s['latency_s']} s |")
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Gate 13 golden questions through the orchestrator.")
    parser.add_argument("ids", nargs="*", help="case IDs to run (default: all)")
    parser.add_argument("--judge", action="store_true", help="grade free-text phrases with EVAL_JUDGE_MODEL")
    parser.add_argument("--allow-writes", action="store_true", help="run C01 (edits and restores one inventory row)")
    args = parser.parse_args()

    configure_stdlib_logging()
    cases = load_cases(args.ids)
    if not await specialist_reachable():
        print("WARNING: the Fulfilment Specialist is not reachable; delegation cases will fail. "
              "Start it: python -m fulfilment_specialist.server\n")
    rt, dead_rt = Runtime(), None
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scored, raw = [], []

    for case in cases:
        if case["id"] in MANUAL or (case["id"] == "C01" and not args.allow_writes):
            reason = MANUAL.get(case["id"], "needs --allow-writes")
            scored.append({"id": case["id"], "category": case["category"], "skipped": True, "reason": reason})
            print(f"  {case['id']:5} skipped ({reason})")
            continue
        started = time.monotonic()
        if case["category"] == "remote_failure":
            dead_rt = dead_rt or Runtime(card_url=DEAD_CARD, timeout=5)
            answer, traces = await run_default(dead_rt, case)
        elif case["category"] == "session_isolation":
            answer, traces = await run_session_isolation(rt, case)
        elif case["id"] == "C01":
            answer, traces = await run_inventory_change(rt, case)
        else:
            answer, traces = await run_default(rt, case)
        verdict = None
        if args.judge:
            from evals.scoring import fact_tokens
            phrases = [p for p in case.get("must_mention") or [] if not fact_tokens(p)]
            verdict = judge(answer, phrases, case.get("must_not_claim") or [])
        result = score_case(case, answer, traces, verdict)
        scored.append(result)
        raw.append({"case": case, "answer": answer, "traces": traces, "score": result})
        print(f"  {case['id']:5} {'pass' if result['passed'] else 'FAIL':4} {result['first_failure'] or '':18} "
              f"{result['header']['outcome'] or '-':16} {time.monotonic() - started:5.1f}s")

    metrics = aggregate(scored)
    previous = previous_metrics()
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (config.EVAL_DIR / f"{run_id}.json").write_text(json.dumps(
        {"run_id": run_id, "settings": config.summary(), "metrics": metrics, "cases": raw}, indent=2, default=str),
        encoding="utf-8")
    md = scorecard_md(run_id, metrics, scored, previous)
    (config.EVAL_DIR / "latest.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    if gate(metrics):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
