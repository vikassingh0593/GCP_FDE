"""The six mandatory demos (brief §13) → demo_outputs/*.md (Step 8, D59).

Each demo runs as a real agent conversation (harness/run_agent.py), so the
"interpreted intent" is the agent's actual routing. For every tool call the
file shows the brief's chain:

    query → interpreted intent → filters → candidates with country/status →
    reranked evidence → evidence sent to Gemini → answer → citation/abstention

and ends with automatic checks against section C (src/eval_scoring.py). The
demos are the cases in tests/eval_set.json that have a `demo_file`.

Run from submission/ (needs Google Cloud; ~5 min):
    source .venv/bin/activate && source env.sh && python src/05_run_demos.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("MEDEVIDENCE_RUN_TAG", "demo")  # test traffic is tagged (D60)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from config import DEMO_OUTPUTS_DIR  # noqa: E402
from eval_scoring import load_cases, score_case  # noqa: E402
from run_agent import converse, describe_call  # noqa: E402


def _table(header: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return out + ["| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in row) + " |" for row in rows]


def _page(c: dict) -> str:
    if not c.get("page_start"):
        return "–"
    return f"p.{c['page_start']}" + (f"–{c['page_end']}" if c.get("page_end") and c["page_end"] != c["page_start"] else "")


def trace_md(call: dict) -> list[str]:
    """Steps 2–5 and 7 of the brief's chain for one tool call."""
    r = call.get("result")
    lines = [f"#### Tool call: `{describe_call(call)}`"]
    if not r:
        return lines + ["Skipped by code (tool-call limit, repeat, or patient case: only `escalate` may run)."]
    lines += ["", "**2. Filters** (hard, applied in SQL before the search; set by code, never by the model)",
              "```json", json.dumps(r.get("filters", {}), indent=1, default=str), "```"]
    if r.get("sql"):
        lines += ["SQL that ran (read-only):", "```sql", r["sql"].strip(), "```"]
    cands = r.get("candidates", [])
    lines += ["", f"**3. Candidates** ({r.get('search_method') or 'no vector search on this path'}: {len(cands)})"]
    if cands:
        lines += _table(["#", "chunk", "document", "countries", "status", "page", "distance"],
                        [[i, c["chunk_id"], c["document_id"], ", ".join(c["countries"]), c["status"], _page(c),
                          f"{c['distance']:.3f}"] for i, c in enumerate(cands, 1)])
    by_id = {c["chunk_id"]: c for c in cands}
    reranked = r.get("reranked", [])
    lines += ["", "**4. Reranked evidence** (Ranking API, top-N)"]
    if reranked:
        lines += _table(["rank", "chunk", "document", "page", "score"],
                        [[i, x["chunk_id"], by_id.get(x["chunk_id"], {}).get("document_id", ""),
                          _page(by_id.get(x["chunk_id"], {})), x["rank_score"]] for i, x in enumerate(reranked, 1)])
    else:
        lines.append("n/a on this path (exact lookup, verified SQL or hand-off: nothing to rank).")
    cards = r.get("cards", [])
    lines += ["", f"**5. Evidence sent to Gemini** (authority order; {len(cards)} card(s))"]
    if cards:
        lines += ["```"] + ["\n".join(card["text"].split("\n")[:2]) for card in cards] + ["```"]
    else:
        lines.append("None: the answer was built by code (not found, ask back, table or rows shown verbatim, hand-off).")
    lines += ["", "**7. Citation / abstention**",
              f"- outcome: **{r['outcome']}**",
              f"- citation check: {r.get('citation_check', 'n/a')}",
              f"- number check: {r.get('number_check', 'n/a')}"]
    if r.get("reasons"):
        lines.append(f"- reasons: {'; '.join(str(x) for x in r['reasons'])}")
    if r.get("escalation_id"):
        lines.append(f"- escalation: {r['escalation_id']} (BigQuery `escalations`, status OPEN)")
    lines.append(f"- latency ms: {r.get('latency_ms', {})}")
    return lines


def case_md(case: dict, turns: list[dict], score: dict) -> list[str]:
    verdict = "PASS" if score["passed"] else f"FAIL (stage: {score['stage']})"
    lines = [f"## {case['id']}: {case['title']}", "",
             f"**Query:** {' → '.join(case['turns'])}", "",
             f"**Expected (section C):** {case.get('expected', '')}", "",
             f"**Result:** {verdict} · {score['seconds']} s", ""]
    for turn in turns:
        lines += [f"### Turn: \"{turn['user']}\"", "",
                  "**1. Interpreted intent** (the agent's routing): "
                  + (", ".join(f"`{describe_call(c)}`" for c in turn["calls"]) or "no tool (answered or asked back itself)"), ""]
        for call in turn["calls"]:
            lines += trace_md(call) + [""]
        lines += ["**6. Answer as shown to the user** (verbatim, D31)", "", "```text", turn["final"], "```", ""]
    retrieval = score["retrieval"]
    lines += ["### 8. Automatic checks against section C", ""]
    lines += _table(["check", "result"], [[k, "PASS" if v else "FAIL"] for k, v in score["checks"].items()]
                    + ([["retrieval: expected page rank (reranked)", retrieval["rank"] or "not in top-N"]] if retrieval else []))
    return lines + [""]


def main() -> None:
    DEMO_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    files: dict[str, list[str]] = {}
    summary = []
    for case in [c for c in load_cases() if c.get("demo_file")]:
        print(f"[demo] {case['id']} {case['title']} …", flush=True)
        turns = converse(case["turns"])
        score = score_case(case, turns)
        summary.append((case, score))
        header = files.setdefault(case["demo_file"], [
            f"# Demo {case['demo_file'][:2].lstrip('0')}: {case['title'].split(':')[0]}", "",
            f"Generated by `src/05_run_demos.py` on {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} "
            "through the agent (`adk` runner). Trace: query → interpreted intent → filters → candidates → "
            "reranked → evidence → answer → citation/abstention.", ""])
        header += case_md(case, turns, score)
        print(f"       {'PASS' if score['passed'] else 'FAIL: ' + str(score['stage'])} · "
              f"{', '.join(score['tools']) or 'no tool'} · {score['seconds']} s", flush=True)
    for name, lines in files.items():
        (DEMO_OUTPUTS_DIR / name).write_text("\n".join(lines), encoding="utf-8")
    index = ["# Demo outputs", "", f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}.", ""]
    index += _table(["case", "demo", "file", "tools", "result", "seconds"],
                    [[c["id"], c["title"], f"[{c['demo_file']}]({c['demo_file']})", ", ".join(s["tools"]) or "none",
                      "PASS" if s["passed"] else f"FAIL ({s['stage']})", s["seconds"]] for c, s in summary])
    (DEMO_OUTPUTS_DIR / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    passed = sum(s["passed"] for _, s in summary)
    print(f"\n{passed}/{len(summary)} demo cases pass · files in {DEMO_OUTPUTS_DIR}")


if __name__ == "__main__":
    main()
