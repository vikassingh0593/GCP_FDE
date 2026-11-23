"""Gate 2-5 experiments: retrieval quality on its own, without the agent.

Runs the retrieval cases of the golden set (exact-ID and paraphrase questions,
plus the stale-version check) straight through search(), so chunk size,
dimension, legs and reranking can be compared on the same questions.

Run from retail-control-tower/ (after scripts.ingest_docs for each table):

    python -m evals.retrieval_eval                                   # doc_chunks, hybrid + rerank
    python -m evals.retrieval_eval --legs dense                      # Gate 4: dense only
    python -m evals.retrieval_eval --legs lexical                    # Gate 4: lexical only
    python -m evals.retrieval_eval --no-rerank                       # Gate 5: without the Ranking API
    python -m evals.retrieval_eval --table doc_chunks_cs256_d768     # Gate 2: chunk size 256
    python -m evals.retrieval_eval --table doc_chunks_cs512_d3072 --dimension 3072   # Gate 3

Prints hit@1, hit@5, MRR, forbidden-version leaks and latency, and saves
output/eval/retrieval_<label>.json for evaluation_report.md.
"""

from __future__ import annotations

import argparse
import json
import time
from statistics import median

from common import config
from evals.scoring import doc_match
from orchestrator.retrieval.search import search

# Gate 4 tests named in the design doc, on top of the golden retrieval cases.
EXTRA = [
    {"id": "G4-dense-failure", "question": "PAY-H205", "expected_docs": ["RB-PAY-004"], "forbidden_docs": []},
    {"id": "G4-lexical-failure", "question": "Units are physically there but promised to someone else's bulk order",
     "expected_docs": ["RB-ALLOC-002@v3"], "forbidden_docs": ["RB-ALLOC-002@v2"]},
]


def cases() -> list[dict]:
    golden = [json.loads(line) for line in config.GOLDEN_QUESTIONS_FILE.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    picked = [c for c in golden if c["category"] in ("exact_id", "paraphrase") and c.get("expected_docs")]
    return picked + EXTRA


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval-only experiments (Gates 2-5).")
    parser.add_argument("--table", default=config.BQ_DOC_CHUNKS_TABLE)
    parser.add_argument("--dimension", type=int, default=config.EMBEDDING_DIMENSION, choices=(768, 1536, 3072))
    parser.add_argument("--legs", default="hybrid", choices=("hybrid", "dense", "lexical"))
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--top-n", type=int, default=config.TOP_N)
    args = parser.parse_args()

    label = f"{args.table}_{args.legs}{'_norerank' if args.no_rerank else ''}"
    rows = []
    for case in cases():
        started = time.perf_counter()
        out = search(case["question"], table=args.table, dimension=args.dimension, top_n=args.top_n,
                     use_cache=False, use_rerank=not args.no_rerank, legs=args.legs)
        latency = round((time.perf_counter() - started) * 1000)
        docs = out.get("_trace", {}).get("docs", [])
        expected = case.get("expected_docs") or []
        ranks = [next((i for i, d in enumerate(docs, start=1) if doc_match(e, [d])), None) for e in expected]
        first = min((r for r in ranks if r), default=None)
        leaked = [f for f in case.get("forbidden_docs") or [] if doc_match(f, docs)]
        rows.append({"id": case["id"], "question": case["question"], "docs": docs, "ranks": ranks,
                     "hit1": first == 1, "hit5": first is not None and first <= 5,
                     "rr": (1 / first) if first else 0.0, "leaked": leaked, "status": out.get("status"),
                     "strategy": out.get("_trace", {}).get("strategy"), "latency_ms": latency})
        print(f"  {case['id']:18} rank {first or '-':>2}  {'LEAK ' + ','.join(leaked) if leaked else '':12} "
              f"{latency:5} ms  {docs[:5]}")

    n = len(rows)
    summary = {"label": label, "table": args.table, "dimension": args.dimension, "legs": args.legs,
               "rerank": not args.no_rerank, "cases": n,
               "hit@1": round(sum(r["hit1"] for r in rows) / n, 3), "hit@5": round(sum(r["hit5"] for r in rows) / n, 3),
               "mrr": round(sum(r["rr"] for r in rows) / n, 3), "leaks": sum(bool(r["leaked"]) for r in rows),
               "latency_ms_p50": median(r["latency_ms"] for r in rows)}
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (config.EVAL_DIR / f"retrieval_{label}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2),
                                                             encoding="utf-8")
    print(f"\n{label}: hit@1 {summary['hit@1']}  hit@5 {summary['hit@5']}  MRR {summary['mrr']}  "
          f"leaks {summary['leaks']}  p50 {summary['latency_ms_p50']} ms")


if __name__ == "__main__":
    main()
