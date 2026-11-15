# Production readiness review

Use this when someone asks whether a system can go live. A readiness review judges evidence, not intentions. "We plan to" doesn't count as done.

## Steps

1. Run Review mode across every stage that applies, if it hasn't been done.
2. Give each stage a verdict with evidence.
3. Answer the 20 readiness questions from the project's real files.
4. Name the level (L1–L4) and the final verdict.
5. Give the shortest ordered list of what must change.

## Stage verdicts

| Verdict | Meaning |
|---|---|
| **Pass** | The checks hold, and you can point to the evidence |
| **Partial** | Some checks hold; say which are missing |
| **Fail** | Open Blockers, or the work is missing |
| **Not applicable** | Say why. Stages 1, 9, 10 and 11 can't be not applicable |

## Final verdict

| Verdict | Rule |
|---|---|
| **Not ready** | Any open Blocker, or any stage at Fail |
| **Ready with conditions** | No Blockers; open High items each have an owner and a date, and the risk is accepted by a named person |
| **Ready** | No Blockers or High items; the 20 questions are answered with evidence; evaluation passes in CI; rollback has been tested |

If several of the final-review answers below are "no", the system is still a prototype. Never soften this. Telling someone they aren't ready is the most useful thing a trainer can do.

## The 20 readiness questions

1. What is the source of truth for each key fact?
2. Which tools are safe to retry?
3. What happens when Gemini is unavailable?
4. What happens when a dependency is unavailable?
5. How is stale evidence detected?
6. How are conflicting sources handled?
7. Who may see sensitive evidence?
8. How are secrets managed?
9. What sensitive fields enter model context?
10. What is logged and retained?
11. How is a bad prompt rolled back?
12. How is a bad policy rolled back?
13. How are model upgrades evaluated?
14. What is the maximum cost per task?
15. What prevents infinite loops?
16. What prevents a premature conclusion?
17. What happens after a process restart?
18. How are duplicate future writes prevented?
19. How does operations debug a bad recommendation?
20. How is business impact measured?

## Final engineering review

Can we explain every action? Every rejection? Identify every evidence source? Detect stale evidence? Survive dependency failure? Stop a loop? Reject an invalid action? Reject premature synthesis? Tell fact from inference? Reproduce the runtime configuration? Measure cost? Roll back? Can operations support this after we leave?

## Failure patterns to reject

1. One giant prompt containing all data.
2. Hard-coded `if/else` presented as semantic orchestration.
3. Gemini directly calling unrestricted tools.
4. Every case calling every tool.
5. Treating confidence as evidence.
6. Treating historical similarity as current cause.
7. Retrying everything.
8. Logging everything.
9. Treating the final answer as the audit trail.
10. Declaring production readiness because one demo succeeded.

**RAG anti-patterns:** "we have a vector DB, so we have RAG"; raising top-K until the answer appears; one chunk size for every source; letting the model invent business meaning; vector RAG for aggregations; treating similarity as confidence; adding reranking without measuring retrieval; citing a document without mapping claims to evidence.

## Stress the design

Pick two or three and ask how the design adapts. A strong design adapts without collapsing:

- An API costs money per call.
- Payment data can't enter Gemini.
- A data feed is delayed by 20 minutes.
- A key API is only 99% available.
- High-value cases require human review.
- Every recommendation needs evidence.
- Customer names can't appear in traces.
- The model must be replaceable without rewriting the orchestrator.

## Report format

```markdown
## Verdict: Not ready | Ready with conditions | Ready
Level: L2. One or two sentences on why.

## Stages
| Stage | Verdict | Evidence or gap |
|---|---|---|

## Blockers
Each one in the Review format.

## Readiness questions
| # | Answered? | Evidence or gap |
|---|---|---|

## Shortest path to ready
1. ...

## How I checked
What was run, what was read, and what was not checked.
```

**A demo asks** "can the model choose the next tool?" **An engineering implementation asks** "can the runtime safely execute the model's decision?" **A production system asks** "can we operate, observe, evaluate, secure, recover, govern and economically sustain this at scale?"
