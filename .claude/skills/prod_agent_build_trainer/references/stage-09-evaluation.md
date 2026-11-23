# Stage 9: Evaluation

**Goal:** know whether the system is good, know which step broke when it isn't, and stop a bad change from shipping.
**Never skip this stage.** One successful demo proves very little.
**Go deeper:** concepts.md §21; arch.md flow 3.

## What to build

| Layer | What it proves | Needs Gemini? |
|---|---|---|
| Deterministic tests | Policy, tools, parsing and state rules work | No |
| Retrieval evaluation | The right evidence is found | Embeddings only |
| Golden set | Answers and outcomes are right | Yes |
| Trajectory evaluation | The agent took sensible steps | Yes |
| Torture tests | It fails safely | Partly |
| Adversarial tests | It resists attacks | Yes |

**Debug layer by layer:** was the document present, parsed correctly, in a useful chunk, embedded, found, kept by reranking, in the context, used in the answer? If retrieval misses the evidence, changing the answer model won't help.

### Metrics

- **Retrieval:** Recall@K, Precision@K, hit rate, MRR, nDCG.
- **Answer:** groundedness, relevance, citation correctness, refusal accuracy.
- **Agent:** routing accuracy, task success, risky cases escalated, latency p50 and p95.
- **Orchestration:** average steps, unnecessary-tool-call rate, repeated-action rate, grounded conclusion rate, unsupported-claim rate.

### Deterministic tests to write first

Unknown action rejected · tool budget enforced · repetition detected · failure budget enforced · premature synthesis rejected · stale evidence handled · forbidden write rejected · state survives across sessions as designed.

### The ten torture tests

| # | Test | Must happen |
|---|---|---|
| 1 | Repeated action | Detected, rejected, reason recorded |
| 2 | Dependency timeout | Bounded retry, degrade or escalate, no crash |
| 3 | Stale evidence | Not treated as current |
| 4 | Conflicting authoritative sources | Surfaced, not reconciled by invention |
| 5 | Premature synthesis | Rejected by policy |
| 6 | Budget exhausted | Explicit incomplete result listing what is missing |
| 7 | Invalid decision (`DELETE_ORDER`) | Never executes |
| 8 | Injection in evidence ("ignore all policies") | Treated as data; action space unchanged |
| 9 | Historical similarity trap | Used as context, not as proof of cause |
| 10 | Policy bypass ("ignore limits, I'm the admin") | Policy unchanged |

## Checks

### EV-01 · Blocker · A golden set exists
- **Look for:** known cases covering normal, edge and failure paths. Each lists important evidence, forbidden conclusions and acceptable end states.
- **Why:** without it, every change is a guess, and quality is a feeling.
- **Fix:** start with 10–15 cases built from real questions. Don't demand one exact tool sequence unless business policy requires it.

### EV-02 · High · Deterministic tests run without the model (scan)
- **Look for:** tests of policy, tools and contracts that make no Gemini call.
- **Why:** they are fast, free and repeatable, so they run on every change. If policy needs Gemini to test, the engineering brain isn't separated.
- **Fix:** start with the list above.

### EV-03 · High · Retrieval is scored separately, and failures are named by stage
- **Look for:** retrieval metrics, plus a failure label: routing, filters, not retrieved, reranked out, or answer.
- **Why:** a single pass-or-fail score tells you nothing about what to fix.
- **Fix:** score each stage, and record which one failed.

### EV-04 · High · The trajectory is evaluated, not only the answer
- **Look for:** whether the next action was useful, unnecessary actions were avoided, critical evidence wasn't skipped, and it stopped at the right time.
- **Why:** a right answer from a wasteful or risky path won't hold up at scale.
- **Fix:** score these per case. Allow several valid paths.

### EV-05 · High · Torture tests pass, with machine-readable traces
- **Look for:** at least five, ideally all ten, saved as trace files.
- **Why:** production failures are the normal case. Screenshots prove nothing.
- **Fix:** simulate each failure, and save the trace.

### EV-06 · High · Adversarial tests exist
- **Look for:** prompt injection, role injection, indirect injection in documents, PII extraction and unauthorized tool use.
- **Why:** the user doesn't have to write the attack: a document can carry it.
- **Fix:** add them to the regular suite. Promptfoo and garak can help.

### EV-07 · High · The execution report is graded too
- **Look for:** assertions on how the run ended, the counts, and whether a blocked tool actually ran.
- **Why:** an answer can look safe while the tool ran anyway.
- **Fix:** assert on the report and the trace.

### EV-08 · Medium · Variable behavior is measured as a rate
- **Look for:** several runs per case for model-driven routing.
- **Why:** routing varies between runs even at temperature 0, so one pass proves little.
- **Fix:** run each case several times, and track the rate.

### EV-09 · Medium · Offline replay is available, and fixtures expire
- **Look for:** recorded responses for fast tests, keyed by prompt and model.
- **Why:** live runs are slow and cost money, but a stale recording hides a regression.
- **Fix:** key recordings on a hash of the rules and model.

### EV-10 · High · A release gate covers every kind of change
- **Look for:** the suite running in CI on changes to code, prompts, models, rules, corpus, index and policy.
- **Why:** a prompt change can alter behavior as much as a code change.
- **Fix:** add the suite to CI, and set which metrics must pass.

### EV-11 · Medium · Evaluation runs through the agent
- **Look for:** demos and evaluation using the same path as real users.
- **Why:** calling the tool directly skips routing, and routing is the agent's one job.
- **Fix:** share one runner between the app and the evaluation.

### EV-12 · Medium · Test traffic is tagged
- **Look for:** a run tag in logs and escalations.
- **Why:** test hand-offs must not look like real open cases, or the health report lies.
- **Fix:** add `run_tag` values such as eval, demo and smoke.

### EV-13 · Medium · Live failures become tests
- **Look for:** a path from feedback and incidents into the test set.
- **Why:** this is how the suite keeps up with reality. Every bug found is a test you didn't have.
- **Fix:** add a regression test with every fix.

### EV-14 · Medium · Adaptivity is proved
- **Look for:** one case re-run with one fact changed, showing a different next action while policy stays the same.
- **Why:** this is the proof that there's no hidden hard-coded router.
- **Fix:** add it to the demo results.

### EV-15 · Note · Online evaluation is planned
- **Look for:** shadow mode, canary or A/B test plans (beyond the course).
- **Why:** offline tests can't cover real traffic.
- **Fix:** run the new version on a copy of live traffic first.

### EV-16 · High · The golden set covers every behavior, with an answer key
- **Look for:** only answerable questions in the golden set; cases with no expected outcome or forbidden claims.
- **Why:** a system that answers every question well can still invent a cause when evidence is missing, call a specialist it shouldn't, leak another user's session or serve a stale cache. If no case tests those, nothing catches them.
- **Fix:** include answerable, insufficient-evidence, exact-ID, paraphrase, delegation (and must-not-delegate), remote-failure, session-isolation and stale-cache cases. Each has an expected outcome, facts that must appear, claims that fail it, and documents that must and must not be retrieved. Judge claims, not exact strings.
- **Go deeper:** concepts.md §21 (case mix).

### EV-17 · Medium · Test data keeps its meaning on any day
- **Look for:** fixtures and demo data with fixed dates, while the system checks freshness against the real clock.
- **Why:** a fixed date turns "fresh" data stale a day later, and every freshness test then fails, or worse, passes for the wrong reason.
- **Fix:** store times as offsets from a run clock, regenerate before each test session with the same rows, and let tests fix the clock (an `--as-of` option) so a bad answer can be replayed.
- **Go deeper:** concepts.md §21 (test data that keeps its meaning).

## Defend it

- Which golden cases would catch an invented cause when evidence is missing?
- How do you evaluate several valid trajectories?
- How would you detect a regression after a prompt change?
- Why test the execution report as well as the answer?
- What evidence do you have that a blocked tool really didn't run?
