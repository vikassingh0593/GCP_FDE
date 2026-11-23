"""Evaluation through the agent (Step 8, D58, D59): ~28 questions by category, scored by stage.

Each case in tests/eval_set.json runs as a real agent conversation, so routing
is scored too. Retrieval (hit@5, MRR) and generation (facts, citations,
refusals, safety) are scored separately, and every failure names the stage
that broke (src/eval_scoring.py). No model judges the answers: the checks are
the expected facts, sources and forbidden documents written in the data.

Outputs:
  output/eval/<run_id>.json   every case: tools, outcome, checks, answer text
  output/eval/latest.md       the scorecard (green / amber / red vs health_thresholds.json)
  BigQuery pipeline_health    one row per metric (stage "eval"), so runs form a trend

Run from submission/ (needs Google Cloud; ~15-20 min):
    source .venv/bin/activate && source env.sh && python src/06_evaluate.py
    python src/06_evaluate.py D4 T1 X2       # only these case IDs
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("MEDEVIDENCE_RUN_TAG", "eval")  # test traffic is tagged (D60)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from config import OUTPUT_DIR  # noqa: E402
from eval_scoring import aggregate, load_cases, load_thresholds, rate, score_case  # noqa: E402
from health import Health  # noqa: E402
from run_agent import converse  # noqa: E402

STATUS = {"green": "pass", "amber": "warn", "red": "fail"}


def scorecard_md(metrics: dict, scored: list[dict], run_id: str) -> str:
    rules = load_thresholds()["eval"]
    lines = [f"# Evaluation scorecard · run {run_id}", "",
             f"{metrics['cases']} questions through the agent · {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} · "
             "deterministic checks (no model judge) · thresholds: `health_thresholds.json`", "",
             "| metric | value | rating | green / amber |", "|---|---|---|---|"]
    for name, rule in rules.items():
        value = metrics.get(name)
        lines.append(f"| {name} | {value if value is not None else 'n/a'} | {rate(value, rule)} | "
                     f"{'≤' if rule.get('direction') == 'below' else '≥'} {rule['green']} / {rule['amber']} |")
    lines += ["", f"MRR: {metrics['mrr']} · p50 latency: {metrics['latency_p50_s']} s · "
                  f"failures by stage: {metrics['failures_by_stage'] or 'none'}", "",
              "| id | category | new | tools | outcome | result | stage | s |", "|---|---|---|---|---|---|---|---|"]
    for s in scored:
        lines.append(f"| {s['id']} | {s['category']} | {'★' if s['new'] else ''} | {', '.join(s['tools']) or 'none'} | "
                     f"{', '.join(s['outcomes'])} | {'PASS' if s['passed'] else 'FAIL'} | {s['stage'] or ''} | {s['seconds']} |")
    failed = [s for s in scored if not s["passed"]]
    if failed:
        lines += ["", "## Failures (review the text: a deterministic check can miss a correct paraphrase)", ""]
        for s in failed:
            bad = [k for k, v in s["checks"].items() if not v]
            lines += [f"### {s['id']} · stage: {s['stage']} · failed checks: {', '.join(bad)}",
                      f"Question: {s['question']}", "", "```text", s["answer"][:1500], "```", ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    wanted = set(sys.argv[1:])
    cases = [c for c in load_cases() if not wanted or c["id"] in wanted]
    health = Health("eval")
    scored = []
    for case in cases:
        print(f"[eval] {case['id']:4} {case['category']:12} {case['turns'][-1][:70]}", flush=True)
        try:
            turns = converse(case["turns"])
        except Exception as exc:  # one broken case must not stop the run
            turns = [{"user": case["turns"][-1], "calls": [], "final": f"ERROR: {str(exc)[:300]}", "seconds": 0}]
        s = score_case(case, turns)
        scored.append(s)
        print(f"       {'PASS' if s['passed'] else 'FAIL (' + str(s['stage']) + ')'} · "
              f"{', '.join(s['tools']) or 'no tool'} · {', '.join(s['outcomes'])} · {s['seconds']} s", flush=True)

    metrics = aggregate(scored)
    rules = load_thresholds()["eval"]
    for name, rule in rules.items():
        value = metrics.get(name)
        if value is not None:
            health.record(name, STATUS[rate(value, rule)], value=value,
                          threshold=f"{'<=' if rule.get('direction') == 'below' else '>='} {rule['green']}",
                          details=f"{metrics['cases']} cases" + (" (subset)" if wanted else ""))
    out = OUTPUT_DIR / "eval"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{health.run_id}.json").write_text(json.dumps({"metrics": metrics, "cases": scored}, indent=1, default=str),
                                               encoding="utf-8")
    (out / "latest.md").write_text(scorecard_md(metrics, scored, health.run_id), encoding="utf-8")
    health.save()
    print("\n" + "\n".join(f"{k:22} {v}" for k, v in metrics.items()))
    print(f"\nScorecard: {out / 'latest.md'}")


if __name__ == "__main__":
    main()
