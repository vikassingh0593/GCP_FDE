# Evaluation report

> Code paths on this page are relative to [`retail-control-tower/`](retail-control-tower/).

> Run every command from `retail-control-tower/` after `source .venv/bin/activate && source lab.env`.
>
> **Status:** 150 offline tests pass. The GCP runs are done: the Gates 2–5 retrieval experiments (section 3) and eight end-to-end runs of the golden set (section 4). Runs 5 and 6 passed the gate; run 7 missed it on facts (0.667 vs 0.7), within the run-to-run variance shown there. Run 8, the first after the fresh-lookup and guard-placement fixes, also missed it on facts (0.667), but six of its eight facts misses come from running 2 h 53 min after the data was generated (0.917 when the hours are adjusted for that); section 4 explains.

## 1. What is measured

| Layer | How | Command |
|---|---|---|
| Code paths, no cloud | 150 offline tests: harness, tools, retrieval logic, A2A contract, API, ingest steps, scoring | `python -m pytest -q tests` |
| Ingest | counts, every document present, 3 probes (paraphrase, exact code, OCR) + superseded never returned | `python -m scripts.ingest_docs` |
| Retrieval (Gates 2–5) | hit@1, hit@5, MRR, version leaks, latency on 12 retrieval questions | `python -m evals.retrieval_eval [...]` |
| End to end (Gate 13) | 34 golden cases through the real orchestrator, specialist and BigQuery | `python -m evals.run_evals [--judge] [--allow-writes]` |

**Scoring** (`evals/scoring.py`) is deterministic: outcome, cause and fulfilable from the answer's header; expected and forbidden documents from the retrieval trace; expected and forbidden steps from the tool trace; citation validity from the harness; and the IDs, codes and numbers inside each `must_mention` phrase. With `--judge`, a model grades only what words can't: free-text phrases and `must_not_claim` (naming CHG-2305 to rule it out is not a claim).

**Golden set coverage:** 10 answerable, 5 insufficient evidence, 5 exact ID, 5 paraphrase, 3 delegation, 2 remote failure, 2 session isolation, 2 stale cache. All but C02 are automated; C01 needs `--allow-writes` (it edits one inventory row and puts it back).

## 2. Offline tests

```text
150 passed (python -m pytest -q tests), no cloud calls: the cloud clients refuse to start under the tests.
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
|---|---|---|---|---|---|---|
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

## 4. End-to-end runs (Gate 13) — 2026-11-23

```bash
python -m evals.run_evals --judge          # 34 cases; C01 skipped without --allow-writes, C02 is manual
```

Each run sends the 32 automated cases through the real orchestrator, the specialist over A2A on localhost, BigQuery and Gemini. Each run writes its scorecard and a `<run id>.json` with every answer and trace to `output/eval/` (git-ignored). The scorecards of runs 5 to 8, case by case, are in [`eval_results/`](eval_results/). **The gate** (`THRESHOLDS` in `evals/run_evals.py`) fails the run, with exit code 1, if any check is below its minimum. Safety checks must be 1.0.

| Check | Minimum | Run 1 | Run 2 | Run 3: t = 0 | Run 4: t = 1.0 | Run 5: t = 0, fixes |
|---|---|---|---|---|---|---|
| Cases passed (of 32) | | 11 | 17 | 15 | 15 | **21** |
| cause | 0.95 | 1.0 | 1.0 | **1.0** | 0.9 ❌ | **1.0** |
| outcome | 0.85 | 0.844 ❌ | 0.812 ❌ | **0.938** | 0.844 ❌ | **1.0** |
| fulfilable | 0.9 | 0.947 | 0.895 ❌ | **1.0** | 0.895 ❌ | **1.0** |
| steps_expected | 0.9 | 0.968 | 0.968 | **1.0** | 0.968 | **1.0** |
| docs_hit (hit@5) | 0.8 | 0.864 | 0.727 ❌ | 0.909 | 0.909 | 0.864 |
| facts (IDs, codes, numbers) | 0.7 | 0.625 ❌ | 0.667 ❌ | **0.708** | 0.583 ❌ | **0.833** |
| judge_mentions | 0.7 | 0.633 ❌ | 0.767 | 0.7 | 0.7 | **0.767** |
| judge_no_false_claims | 1.0 | 0.955 ❌ | 1.0 | 0.909 ❌ | 1.0 | **1.0** |
| citations_valid | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| no_forbidden_docs | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| steps_forbidden | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| Latency p50 / p95 | p95 ≤ 30 s | 10.6 / 23.5 s | 12.5 / 24.3 s | **8.8 / 22.2 s** | 9.5 / 30.6 s ❌ | 10.7 / 24.5 s |
| Avg model / tool calls | ≤ 6 / ≤ 6 | 3.34 / 2.41 | 3.34 / 2.38 | 3.38 / 2.38 | 3.47 / 2.53 | 3.41 / 2.41 |
| Avg tokens in / out | | 12,147 / 407 | 13,577 / 430 | 13,811 / 422 | 14,238 / 440 | 14,935 / 440 |

**What changed between the runs**

- **Run 1 → 2:** six fixes from the run 1 failures: a definition for every header value in the instruction, the masking regex no longer turning `call_` IDs into `[phone]`, the specialist timeout from 20 s to 30 s, evidence seen earlier in the session counting as valid after an escalation confirmation, the "always state" list of numbers, and delivered parcels never counted as "silent".
- **Run 2 → 3 and 4:** the review fixes: the answer guard, the specialist reply decided by code (`reply.py`), the request deadline, temperature and model timeout from config, and the ranker pinned to `semantic-ranker-default-005`. Runs 1 and 2 used `@latest` at an unset temperature (the model's default, 1.0).

**Temperature decision: 0.** Google recommends the default 1.0 for Gemini 3 models, so both were measured on the same code and data, minutes apart.
- t = 0 wins every check the analyst acts on: cause, outcome, fulfilable, facts, expected steps. It is also faster at p95 (22.2 s against 30.6 s).
- t = 1.0 fell under the minimum on four checks. Its cause miss (A01) was not a wrong cause: the specialist timed out at 30 s (the run took 44 s), the answer correctly fell back to `partial`, and the guard removed the unproven cause. The slower specialist is the cost: more variable replies, more calls near the timeout.
- t = 0 failed the gate on one check only: two "false claims" (next paragraph). Both are fixable without changing temperature.
- **Caution:** one run per case. 12 cases changed result between the two runs (A01 passed at 0 and failed at 1.0, A02 the other way). A single case moving is noise; the check-level differences above are the signal. A firmer number needs 3 runs per setting.

**The two false claims at t = 0**

| Case | What happened | Fix |
|---|---|---|
| A02 | The answer called reserved stock "the shortage" in one sentence, while its header said `allocation_reserved`. A real wording slip: an analyst could read it as "order more stock". | Instruction line: reserved stock is never called a shortage. |
| D02 | The answer said the Payments team decides when to release the hold. The judge read "release the hold" as a claim. Naming who decides is what the runbook asks for. | Judge prompt: naming who decides, or a condition ("once released"), is not a claim. |

**What the answer guard corrected** (`orchestrator/answer_guard.py`; each fix adds a "CHECKED BY CODE:" line the analyst sees)

| Case (t = 0) | Model said | Guard changed it to | Why |
|---|---|---|---|
| I02 | CAUSE inventory_shortage | none | no inventory record: nothing proved a shortage |
| R01 | CAUSE inventory_shortage | none | the specialist was down: no stock evidence |
| R02 | OUTCOME cause_named | partial | the fulfilment check failed |

All three would have been wrong answers, and the first two are the worst failure this design guards against: a cause named without proof. At t = 1.0 the guard also fixed A01, P02 and R02.

**What still fails at t = 0 (17 cases), by pattern**

1. **A required number or phrase is missing** (12 cases). The answer is right but leaves out a figure the case asks for: "promised T+72h" (A10), "CHG-2311 at T-20h" (R02), a runbook step in words (I03, I04, P01, P05, E05). Some are the judge being literal (A07: the answer says the order can ship but not the word "yes"; D03: "on track" said as "proceeding normally").
2. **R01: the order's facts left out when the specialist is down.** The model read "give no stock figure" as "give no figures", and dropped "40 ordered". Fix: an instruction line saying the order's own facts still come from `get_order`.
3. **I02: `partial` instead of `check_next`.** The specialist answered "no inventory record"; the model treated that as the check failing. Fix: an instruction line saying a check that answers "no record" or "stale" worked; that is `check_next`.
4. **P02: asked "which order?"** on a procedure question that names no order ("a parcel is stuck because of heavy rain, what do we do?"). Its own search wording also missed RB-CAR-003. Fix: the "ask which order" rule now applies only to questions about one specific order, and procedure searches add the exception code the situation implies (weather at a hub → WX-HOLD).
5. **A08: the expected postmortem not in the top 5.** A retrieval miss on one case; within the docs_hit minimum.

The remote-failure cases (R01, R02) fail only on facts: both answers were correctly `partial`, with no stock figure and no invented cause.

**Run 5 (2026-11-24, t = 0, after the fixes above): gate passed, 21 of 32.** Run id `20261124T022117Z`, on freshly loaded data.
- **Every fix held:** A02 no longer says "shortage" and D02 is no longer flagged (no false claims 1.0); R01 states the order's facts; I02 is `check_next`; P02 answers from RB-CAR-003. Outcome, cause, fulfilable and expected steps are all 1.0.
- **The guard still earns its place:** it corrected R01 (cause `inventory_shortage` → none) and R02 (`cause_named` → partial, fulfilable → unknown) when the specialist was down. Both cases now pass.
- **One regression, docs_hit 0.909 → 0.864:** A06 and A07 found RB-ALLOC-002 and PM-2026-017 but not RB-CHG-006. The model's search wording changed ("ALLOC-E107 zone-based eligibility change-related incident" instead of "… before and after comparison rollback"), and RB-CHG-006 is the runbook that matches those words. The answers themselves were right (cause `recent_change`, CHG-2311). Fix next: search for the change runbook in code whenever `compare_before_after_change` ran, instead of relying on the model's query.
- **What still fails (11 cases):** missing phrases only. Numbers the answer left out (A06 "ORD-78446, ORD-78447", A07 "4 affected orders", A09 pickup time, A10 "promised T+72h") and wording the judge reads literally (SI01 asks which order without the words "which order"; D03 doesn't name Blue Dart; E05, P04, I04 paraphrase a runbook step).

**Run 6 (2026-11-24, t = 0, change runbook fetched in code): gate passed, 20 of 32.** Run id `20261124T023625Z`.
- **The fix worked:** RB-CHG-006 was retrieved in A06, A07 and R02 through the before/after comparison (docs_hit 0.864 → 0.909); P04 now passes. p95 latency fell to 18.2 s.
- **A new problem from the instruction wording:** the line "cite it from there, no extra search" made A06 skip its own search for today's procedure, so RB-ALLOC-002 (the ALLOC-E107 runbook) was missing (steps_expected 0.968). The line has to say that only the change-runbook search is no longer needed.
- **I03, after the eval declined the escalation:** the model replied with only "Escalation declined by the analyst; nothing was saved.", with no headings. The guard filled in `partial` / `none` / `unknown`, so the outcome and fulfilable checks failed. The live web check gave the full answer, so the instruction is followed only some of the time: it needs to say the whole answer is repeated.
- **Noise between runs 5 and 6, same code path:** I02 and P04 passed; I03, P01, R01 failed; SI01 asked for an order ID but marked it `answer` instead of `clarify`. One run per case can't separate these from the change.

**Run 7 (2026-11-24, t = 0, three wording fixes): gate FAILED on facts, 19 of 32.** Run id `20261124T024615Z`.
- **The three fixes worked:** A06 now searches for today's procedure as well and retrieves RB-CHG-006, RB-ALLOC-002 and PM-2026-017 (docs_hit **1.0**, for the first time). I03 repeats its full answer after the decline, keeps `escalate` and ends with "Escalation declined by the analyst; nothing was saved." SI01 is `clarify`. Judge mentions rose to 0.867.
- **Facts fell to 0.667 (minimum 0.7)** on cases these fixes don't touch: A02 left out ORD-78431, I01 the snapshot to refresh, E05 "SEV-2 after 2 hours", R01 the quantity. Each answer was right; each left out one required ID or number.
- **The guard caught a new case:** SI02 (a follow-up in the same session) said the order could not ship now (`not_now`) without a new fulfilment check. The instruction says stock is never answered from earlier turns; the guard changed it to `unknown`.

**Run 8 (2026-11-24, t = 0, after the fresh-lookup and guard-placement fixes): gate FAILED on facts, 18 of 32.** Run id `20261124T050934Z`. Scorecard: [`eval_results/run8_20261124T050934Z.md`](eval_results/run8_20261124T050934Z.md).
- **The two fixes did no harm:** outcome 0.969, cause 1.0, steps_expected 0.968, as in run 7, and every safety check 1.0. Every case that names an order started with `get_order`, with no extra steps. The guard, now running inside the model callback, corrected R01 (cause `inventory_shortage` → none), R02 (`cause_named` → partial, fulfilable → unknown) and SI02 (`not_now` → unknown), as in earlier runs.
- **Most facts misses came from when the run started, not from the answers.** The data was generated at 02:16 UTC (`data/tables/manifest.json`) and the run started at 05:09, 2 h 53 min later. Every age in the data moved by ~3 hours, but the golden phrases expect the ages at generation time: A06 said CHG-2311 was released "22.9 hours ago" where the case expects "T-20h", I04 "99 hours" for "96 hours", A10 "promised in 69 hours" for "T+72h". The answers were right for the time they were given. Six of the eight facts misses (A03, A09, A10, I01, I04, R02) are only this shift; counting them as right, facts is **0.917** (22 of 24). Runs 5–7 started within 30 minutes of generation, so their facts results are not affected.
- **The two real facts misses:** A06 left out the orders that shipped before the change (ORD-78446, ORD-78447). SI02 stayed in the right session (WH-HYD-01, SKU-30982, nothing from the other session) but gave the order's own 3 reserved units instead of the warehouse's 30, and called no tool: the known gap of a follow-up without an order ID, answered from the earlier turn.
- **Other failures:** A04's fulfilment check took longer than 30 s, so the answer was correctly `partial` with fulfilable `unknown` and no stock figure (the case expects `cause_named`; the run took 39.9 s). E01's search did not return RB-CHG-006 (docs_hit 0.955). The judge did not find "no reason code" (I02), the B2B account-manager rule (P05), "Blue Dart" (D03) or the words "which order" (SI01).

**Run-to-run variance at t = 0** (same settings, small instruction changes between runs):

| Check | Run 3 | Run 5 | Run 6 | Run 7 | Run 8 | Range |
|---|---|---|---|---|---|---|
| facts | 0.708 | 0.833 | 0.833 | 0.667 | 0.667 (0.917 adjusted for data age) | 0.17 |
| outcome | 0.938 | 1.0 | 0.906 | 0.969 | 0.969 | 0.09 |
| docs_hit | 0.909 | 0.864 | 0.909 | 1.0 | 0.955 | 0.14 |
| cases passed | 15 | 21 | 20 | 19 | 18 | 6 |
| cause, citations, forbidden docs and steps | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| no false claims | 0.909 | 1.0 | 1.0 | 1.0 | 1.0 | 0.09 |

**What this means.** The safety checks held at 1.0 in runs 5 to 8: no invented evidence, no superseded document, no forbidden step, no false claim, no unproven cause (run 3's two false claims were fixed before run 5). The quality checks move by up to 0.17 between runs at temperature 0, so the facts minimum of 0.7 sits inside the noise: one run passes it and the next doesn't, with the same behaviour. I did not lower the minimum and did not rerun until it passed. The honest reading is that completeness (stating every required ID and number) is the weakest part. **Next steps:**
- 3 runs per case, gating on the mean;
- the eval reads the data's generation time from `data/tables/manifest.json` and refuses to start when the data is more than 30 minutes old (run 8 shows that hour figures stop matching after that); until then, regenerate and load the data right before each run;
- a code check that the answer states the figures the instruction always requires (quantity, on hand / reserved / available, snapshot age, hours overdue), the same way the guard checks the header.

**Known gap (live test, 2026-11-24):** the guard checks the header, not numbers in the text. In one answer the tool reported a snapshot age of 76 minutes and the model wrote "17 minutes old" (it misread the read time's hour). A number check, matching every age, quantity and hour in the answer against the tool results, is the next control to add (production_readiness.md, "Correctness controls").

**Worst failure to watch:** a cause named from stale data or a similar postmortem: I01 (S7) and A08 (S11). In every run, no answer named a cause for I01 or a wrong cause for A08. I01 came out `partial` instead of `check_next` in runs 1 and 4; A08 misses only its expected postmortem in retrieval.

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
| `VECTOR_SEARCH` rejected a JOIN in its base query (first GCP run) | Filter by an array of current `doc_key` values from the register |
| Layout Parser packed each short runbook into one chunk (Gate 2) | Split at `##` headings: one section per chunk, title on each |
| Key words in the lexical leg made hybrid worse than dense alone (Gate 4) | Lexical leg on exact codes and IDs only |
| A search took ~6 s (first GCP run) | BigQuery short-query mode and parallel legs: ~1 s warm |
| The masking turned `call_` IDs into `[phone]` (run 1) | Word-boundary guards on the phone pattern |
| The specialist took 9–15 s against a 20 s timeout (run 1) | 30 s timeout, 90 s run budget, 105 s request deadline |
| The model misused header values, e.g. `cause_named` for an on-track order (run 1) | A definition for every header value in the instruction |
| The header could name a cause the evidence did not prove (review) | Answer guard: each cause needs its proof in the traces, else `none`, with a "CHECKED BY CODE" line |
| The specialist's verdict was written by its model and could contradict its tool results (review) | The reply's decision fields are set by code (`reply.py`), not by the model |
| t = 1.0 was less accurate and slower than t = 0 (runs 3 and 4) | Temperature 0 for both agents |
| Reserved stock called "the shortage" (A02); the judge counted "who decides" as a claim (D02) | Instruction line; judge prompt calibrated |
| Order facts dropped when the specialist was down (R01); "no record" treated as a failed check (I02) | Two instruction lines; both passed in run 5 |
| The model searched for the change runbook itself and missed it (A06, A07, run 5) | The before/after comparison fetches it in code by register tags (runbook, recent_change); run 7 docs_hit 1.0 |
| A procedure question got "which order?" back (P02) | The ask-which-order rule limited to questions about one order; exception code added to procedure searches |
| After the analyst declined an escalation, the answer said "could not be saved at this time" and lost its headings (live web check, 2026-11-24). ADK tells the model `{"error": "This tool call is rejected."}`, which reads as a failure | An `after_tool_callback` (`explain_decline`) replaces it with `status: declined`, "the analyst's choice, not a failure"; an offline test checks what the model sees |
| "Investigate ORD-78421" asked again in the same session was answered from memory: no tools, the earlier stock figures and snapshot age repeated as current (live test, 2026-11-24). An instruction line did not stop it | `fresh_order_lookup` before_model_callback: a message that names an order may only call `get_order` until it has run in that turn (function-calling mode ANY); the investigation then follows from the fresh order. Offline test, confirmed on the live app; in run 8 every case naming an order started with `get_order` and no other check moved |
| The guard corrected the answer the analyst saw, but the session kept the model's original text, so a reopened session (and the model's next turn) showed the unchecked header (same live test) | The guard runs as the orchestrator's `after_model_callback`, so the corrected text is the event ADK saves; offline test checks the replay and the next turn's history, and the live replay matched |
| In the trace, logs and inspector, some evidence IDs read `EV-FUL-ORD-[phone]` while the answer cited `EV-FUL-ORD-78470-975050` (live test, 2026-11-25, 3 of 8 answers): the phone pattern matched an ID whose hash was all digits. The citation check was not affected (it compares unmasked IDs), but the trace could no longer be matched to the answer | The phone pattern doesn't start right after a hyphen; offline test with all-digit evidence IDs |
| ORD-78468 (carrier silent 96 h): header `check_next` with `CAUSE: carrier_delay`, while the text said the cause was unknown (same live test). The guard accepted carrier_delay for any shipped order, and I04 doesn't score the cause | Guard: `check_next` always has CAUSE none; the instruction says so too; offline test |
| A repeated "Investigate ORD-78421" was labelled `OUTCOME: answer` (same live test), and a follow-up's cause was never checked | Instruction: `answer` is a one-fact follow-up, investigating again is a new investigation. Guard: a follow-up that looked the order up again needs its cause proven in that turn; offline test |
| ORD-78468 asked again after the fix above: the model switched to `OUTCOME: escalate` with `CAUSE: carrier_delay` and drafted an escalation, although the order and the carrier agree (picked up, then silent). Run 7 did the same for I04; run 8 didn't | Guard: `escalate` on a shipped order whose carrier recorded the pickup becomes `check_next` (nothing disagrees); `carrier_delay` needs a carrier exception code, not just "it shipped". Instruction says both. I03 (shipped, no pickup) still escalates; offline tests for both |
