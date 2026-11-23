# Evaluation report

> Code paths on this page are relative to [`retail-control-tower/`](retail-control-tower/).

> Run every command from `retail-control-tower/` after `source .venv/bin/activate && source lab.env`.
>
> **Status:** offline tests run and pass; the GCP runs (Gates 2–5 experiments and the full golden set) have not been run yet. The commands below produce every number this report needs. Paste the outputs into the marked sections.

## 1. What is measured

| Layer | How | Command |
|---|---|---|
| Code paths, no cloud | 116 offline tests: harness, tools, retrieval logic, A2A contract, API, ingest steps, scoring | `python -m pytest -q tests` |
| Ingest | counts, every document present, 3 probes (paraphrase, exact code, OCR) + superseded never returned | `python -m scripts.ingest_docs` |
| Retrieval (Gates 2–5) | hit@1, hit@5, MRR, version leaks, latency on 12 retrieval questions | `python -m evals.retrieval_eval [...]` |
| End to end (Gate 13) | 34 golden cases through the real orchestrator, specialist and BigQuery | `python -m evals.run_evals [--judge] [--allow-writes]` |

**Scoring** (`evals/scoring.py`) is deterministic: outcome, cause and fulfilable from the answer's header; expected and forbidden documents from the retrieval trace; expected and forbidden steps from the tool trace; citation validity from the harness; and the IDs, codes and numbers inside each `must_mention` phrase. With `--judge`, a model grades only what words can't: free-text phrases and `must_not_claim` (naming CHG-2305 to rule it out is not a claim).

**Golden set coverage:** 10 answerable, 5 insufficient evidence, 5 exact ID, 5 paraphrase, 3 delegation, 2 remote failure, 2 session isolation, 2 stale cache. All but C02 are automated; C01 needs `--allow-writes` (it edits one inventory row and puts it back).

## 2. Offline tests

```text
116 passed (python -m pytest -q tests), no cloud calls: the cloud clients refuse to start under the tests.
```

What they prove without GCP: the harness refuses runs without context, blocks loops and budgets, and flags invented evidence IDs; a dead specialist gives a partial answer; a declined escalation writes nothing; stale inventory gives "unknown"; no inventory row isn't zero; the Agent Card shows one skill and no internal tools; a register change invalidates the retrieval cache; ingest fails on a missing PDF, a stale processor ID, a retired parser version or a blank scan.

## 3. Retrieval experiments (Gates 2–5) — run 2026-11-23

```bash
python -m scripts.ingest_docs                                   # doc_chunks (512, 768)
python -m scripts.ingest_docs --chunk-size 256                  # doc_chunks_cs256_d768
python -m scripts.ingest_docs --dimension 3072                  # doc_chunks_cs512_d3072
python -m evals.retrieval_eval                                  # baseline
python -m evals.retrieval_eval --table doc_chunks_cs256_d768    # Gate 2
python -m evals.retrieval_eval --table doc_chunks_cs512_d3072 --dimension 3072   # Gate 3
python -m evals.retrieval_eval --legs dense                     # Gate 4
python -m evals.retrieval_eval --legs lexical                   # Gate 4
python -m evals.retrieval_eval --no-rerank                      # Gate 5
```

12 questions: the 10 exact-ID and paraphrase golden cases + the 2 Gate 4 tests. 62 section chunks from 13 documents.

| Run | hit@1 | hit@5 | MRR | Version leaks | p50 ms |
|---|---|---|---|---|---|
| **Baseline: sections / 768 / hybrid (codes) / rerank** | **0.917** | **1.0** | **0.958** | 0 | 1,025 |
| Gate 2: whole-document chunks (Layout Parser at 512, no section split) | 0.833 | 1.0 | 0.917 | 0 | 1,057 |
| Gate 3: dimension 3072 | 0.917 | 1.0 | 0.958 | 0 | 3,580 |
| Gate 4: dense only (with rerank) | 0.917 | 1.0 | 0.958 | 0 | 1,101 |
| Gate 4: lexical only (with rerank) | 0.75 | 0.917 | 0.833 | 0 | 1,001 |
| Gate 5: hybrid, no rerank | 0.75 | 0.917 | 0.833 | 0 | 688 |
| Gate 5: dense only, no rerank | 0.667 | 0.917 | 0.764 | 0 | 705 |
| *First version: hybrid with key words, no rerank* | *0.583* | *0.833* | *0.694* | *0* | *739* |

**What the numbers decided**

- **Gate 2, chunking:** Layout Parser's chunk size is a maximum, so at 512 tokens it packed each short runbook into ONE chunk (13 chunks for 13 documents). Splitting at the `##` headings (62 chunks, one per section) raised hit@1 from 0.833 to 0.917. Kept: one section per chunk. Chunk size 256 was not run: every section is already under 256 tokens, so it would only change how the parser packs, not the result.
- **Gate 3, dimension:** 3072 gave the same quality and searched ~3x slower. Kept: 768.
- **Gate 4, dense vs lexical:** the first lexical leg (exact codes + key words) made hybrid WORSE than dense alone without reranking (0.583 vs 0.667 hit@1): key-word counts pulled wordy postmortems above the right runbook (P03, P04). Changed to exact codes and IDs only; hybrid then beat both legs (0.75 hit@1 without rerank). With rerank, hybrid and dense tie on this small corpus; hybrid is kept because it ranks exact codes higher before reranking (E03, E04, PAY-H205), which matters as the corpus grows.
- **Gate 5, rerank:** raises hit@1 from 0.75 to 0.917 and hit@5 from 0.917 to 1.0 for ~0.3 s. Kept on every query.
- **Latency:** the first measurement was ~6 s per search. Two changes brought it to ~1 s warm: BigQuery short-query mode (no job for small reads) and running the two legs in parallel. The first search in a process still takes ~4 s (clients and the register read).

**Decision rule** (written before the run): keep 512 and 768 unless the alternative raises hit@5 or MRR; hybrid must beat each leg alone on the two Gate 4 tests; keep the reranker if it raises hit@1. **Outcome:** all held after the lexical-leg change above.

## 4. End-to-end run (Gate 13) — *to fill after the first GCP run*

Paste `output/eval/latest.md` here.

| Metric | Result | Target |
|---|---|---|
| Case pass rate | | ≥ 0.8 |
| Outcome correct | | ≥ 0.9 |
| Documents hit@5 | | ≥ 0.9 |
| Forbidden documents | | 0 |
| Valid citations | | 1.0 |
| Trajectory (expected / forbidden steps) | | ≥ 0.9 / 1.0 |
| Latency p50 / p95 | | p95 ≤ 30 s |
| Avg model / tool calls | | ≤ 6 / ≤ 6 |

**Worst failure to watch:** a cause named from stale data or a similar postmortem: I01 (S7) and A08 (S11).

## 5. Manual case C02 (retrieval cache after a new runbook version)

1. Ask "What should we do about a shipment with a WX-HOLD exception?" (cached).
2. Publish RB-CAR-003 v5 with a changed WX-HOLD instruction: add the source in `data/docs_source/`, run `python data/build_docs.py`, and mark v4 superseded and v5 current in the register.
3. `python -m scripts.load_data` (register + bucket), then ask again **before** re-ingesting: v4 must be gone (register check) and the cache must miss (register fingerprint).
4. `python -m scripts.ingest_docs`, ask again: the answer uses v5.

## 6. What changed because of evaluation

| Finding | Change |
|---|---|
| ADK's automatic Agent Card listed every internal tool (offline check) | Hand-built card with one skill; a test fails if a tool name appears |
| A specialist sub-agent takes over the conversation and leaks raw A2A errors | Specialist wrapped as a tool with a timeout and a contract check |
| A stopped run gave no answer; blocked calls counted as failures (scripted-model tests) | Soft/hard stops with a closing call; harness blocks are not failures |
| The specialist's reply could carry an invented evidence ID (end-to-end A2A test on localhost) | Its harness checks the reply's evidence IDs |
| Chunks without a heading never matched a key word (review: NULL in BigQuery CONCAT) | IFNULL on the section in the lexical leg |
| *(from the first GCP run)* | |
