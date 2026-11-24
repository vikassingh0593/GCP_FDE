# Capstone 2 — Retail Order Exception & Supply Chain Control Tower

## Problem statement
A national retailer has warehouses, stores and carriers. Orders become delayed due to inventory shortage, allocation, carrier status, payment hold, warehouse disruption or recent changes.

Example: **Investigate ORD-78421. Why is it delayed, can it be fulfilled from the assigned warehouse, and what evidence supports the conclusion? If evidence is insufficient, say what should be checked next.**

This combines live structured state with historical/unstructured knowledge.

## Suggested roles
Order Exception Orchestrator; Fulfilment Specialist (strong A2A candidate); Operations Knowledge Specialist (RAG); optional Customer Communication Specialist.

Possible sources: BigQuery orders/inventory, carrier tool/API, warehouse events, runbooks, postmortems, change logs.

## Structured-vs-RAG checkpoint
| Source | Embed? | Structured/tool? | Why? |
|---|---|---|---|
| current order | No | Tool | Live state looked up by exact order ID, owned by the order system. |
| current inventory | No | Tool (inside the Fulfilment Specialist, reached over A2A) | Changes constantly, and exact quantities decide the answer, so it must be read fresh. |
| carrier event | No | Tool | Time-stamped carrier status events, where the latest event and its time matter. |
| warehouse event | No | Tool | Live, time-stamped disruptions (outage, dock closed, system down) owned by the warehouse; direct evidence the warehouse can't ship now. |
| runbook | Yes | Metadata filters | Stable how-to text, searched by meaning; it says how to check, not what is true. |
| historical postmortem | Yes | Mixed | Similar past incidents suggest where to look, but never prove today's cause. |
| recent change | Optional | Mixed (structured first) | Filtered by time and scope to find what changed just before the delay. |

Ask why current inventory is fundamentally different from a troubleshooting manual.

**Answer:** inventory is current state that must be queried fresh, while a manual is stable knowledge that is retrieved by meaning.

## Causality checkpoint
Is historical similarity current-cause evidence? What current evidence is required? How will output separate observation/inference? Can RAG suggest inspection without asserting the same cause?

**Answer:** No. A similar past incident is only a hint about what to check, and the agent names a cause only after current data (order, inventory, carrier events, change log) confirms it. The output labels each point as an observation (a fact from data, with its source and time), an inference (the agent's conclusion) or an unknown (what to check next).

## Freshness/cache checkpoint
| Data | TTL | Why | Key includes |
|---|---|---|---|
| order | 0–10 min, never longer than the source's refresh cycle | Status changes during the day and a cache can't be fresher than its source; if a fresh read is quick, skip the cache. | Order ID + user's access scope |
| inventory | 0 sec (no cache) | Changes constantly and exact quantities decide the answer, so always read fresh. | Warehouse + SKU |
| runbook retrieval | 1 day, cleared when a runbook is updated | Runbooks change rarely, and only through a new version. | Question text + filters + index version |
| query embedding | Weeks, until the embedding model changes | The same text with the same model always gives the same vector. | Question text + embedding model and version |
| final RCA | 0 sec (no cache) | Built on live data, so any change to the order or inventory makes it wrong. | Order ID + times of the evidence used (if ever cached) |

## A2A checkpoint
Define the Fulfilment Specialist Agent Card. Why agent rather than `check_inventory()`? What remains opaque? Can parent return partial evidence if specialist is down?

**Answer:**
- **Agent Card:** name, URL and one skill, "fulfilment check": given an order ID, it says whether the assigned warehouse can fulfil it (yes / no / unknown), with the evidence and the time the data was read.
- **Why an agent:** fulfilment takes several steps and judgment (find the order's warehouse and SKU, check available rather than reserved stock, compare, explain any shortfall), and the fulfilment team owns and releases it separately. The inventory lookup is one tool inside it.
- **Opaque:** its instructions, tools, data sources and reasoning steps. The orchestrator sees only the card and the answer.
- **Specialist down:** yes. After a timeout, the orchestrator returns the evidence it has (order, carrier events, recent changes), marks the fulfilment check "unavailable", lists it under "check next", and never guesses stock.

## Minimum acceptance
Operational data not blindly used as RAG memory; retrieval decision demonstrated; justified multi-agent topology; independent A2A specialist; session investigations; freshness-aware cache; correlation ID across orchestrator→A2A→tools; no similarity-as-causality; safe partial failure; retrieval/trajectory evaluation.

## Architecture Decision Matrix — complete before coding

| Decision | Options to consider | Your selection | Why / evidence |
|---|---|---|---|
| UI | ADK Web / FastAPI+HTML / Streamlit / Other | FastAPI + HTML | ADK Web is a developer testing tool with no sign-in or custom screens; FastAPI + HTML gives a real web experience with our own API, sign-in and per-analyst sessions. Debugging uses the terminal runner (orchestrator/cli.py), which prints the harness report; ADK Web sends no correlation ID, so the harness refuses it by design. |
| Orchestration | Supervisor / Semantic router / Planner-worker / Hybrid | Supervisor | One orchestrator owns the investigation, picks the next step from the evidence, delegates fulfilment to the specialist and combines the results; limits and policy are enforced in code. |
| Agents | 2 / 3 / 4+ | 2 | Orchestrator plus the Fulfilment Specialist (A2A). Runbook and postmortem search is a tool, not an agent: it retrieves, it doesn't decide. |
| Knowledge store | BigQuery / Vertex AI Vector Search / Hybrid | BigQuery | Structured data is already in BigQuery, and its vector search handles a small runbook and postmortem set, so there is one store. Vertex AI Vector Search pays off at millions of vectors. |
| Retrieval | Dense / Lexical / Hybrid / Query-routed | Hybrid (dense + lexical) | Dense finds paraphrases ("stock held for other orders" → allocation runbook); lexical finds exact codes and IDs (warehouse IDs, exception codes). |
| Chunking | Fixed / Structure-aware / Parent-child / Semantic | Structure-aware sections for search, whole document for the answer (parent-child) | Runbooks and postmortems have headed sections, so search ranks one section at a time. The first full eval showed the decision rules sit in the Escalation section, which rarely ranks, so the model gets the whole (short) document. |
| Chunk target | 256 / 512 / 1024 tokens / Other | ~512 to start | Roughly one runbook procedure or postmortem section; confirm by comparing with 256 on the golden questions. |
| Embedding dimension | Lower / Medium / Higher supported dimension | Lower (768) to start | The corpus is small, so quality decides, not storage; compare with a higher size on the golden questions and keep the smaller one unless quality improves. |
| Reranking | None / Top-N / Conditional | Top-N | Retrieve about 20 candidates, rerank them (Vertex AI Ranking API) and pass the best 3–5 to Gemini; the cost is small at demo scale. |
| Session backend | In-memory demo / DB-backed / Vertex-managed | DB-backed | Investigations survive restarts and each analyst's sessions stay separate, so the demo is close to production; Vertex-managed sessions are the production step. |
| Long-term memory | None / ADK MemoryService / external | None (preferences in user state) | Order and inventory data must always be read live, and recalling old conclusions would bring back similarity-as-causality; postmortems already cover history. |
| Context control | Top-K / token budget / summarization / hybrid | Hybrid | Only the top 3–5 evidence chunks, a token budget per turn, and older turns summarized; evidence values (IDs, quantities, times) are never summarized. |
| Cache | embedding / retrieval / tools / synthesis / multi-layer | Multi-layer (by data type) | As in the freshness table: query embeddings and runbook retrieval cached, order data briefly, inventory and the final RCA never. |
| MCP | None / tools / retrieval service / Other | None in v1 | Not in the minimum acceptance; our data tools are local, and A2A already shows the remote boundary. Add an MCP server later if other agents need these tools. |
| A2A | None / one remote specialist / multiple | One remote specialist | The Fulfilment Specialist runs as its own service with its own lifecycle, which shows independent failure. |
| Failure | fail closed / partial / fallback / human escalation | Partial + human escalation | Specialist down → partial answer marked "unavailable"; missing or conflicting evidence → escalate to an analyst with what to check next; missing identity → fail closed; no silent fallback. |
| Evaluation | golden Q&A / retrieval / trajectory / combined | Combined | Golden Q&A for answers, retrieval checks for runbooks and postmortems, trajectory checks for tool and specialist calls. |
| Observability | logs / trace / correlation IDs + metrics | All | One correlation ID from the orchestrator through A2A to the tools, a trace on both agents, and metrics for latency, tool calls, cache hits and failures. |

Before locking the architecture:
1. What requires reasoning and what is deterministic software?
2. Which component deserves to be an agent rather than a tool?
3. What survives one invocation, one session, or multiple sessions?
4. What is the main correctness/latency/cost risk?

- **Reasoning responsibilities:** choosing what to check next, turning evidence into a likely cause, explaining it, and the specialist's fulfilment judgment.
- **Deterministic responsibilities:** data lookups, the stock comparison, freshness checks, cache, limits, access control, timeouts and the correlation ID.
- **Agent boundaries:** Orchestrator (owns the investigation and the analyst conversation) and Fulfilment Specialist (remote over A2A, owns the fulfilment answer); knowledge search is a tool.
- **State/memory lifetimes:** one call = scratch results; one session = the current order and its evidence; across sessions = analyst preferences only; order and inventory data are never stored, always read live.
- **Primary risk:** correctness: naming a wrong cause from stale data or a similar past incident. Next: latency and cost from the extra A2A hop.

# Guided Engineering Walkthrough

### Gate 1 — Data contract
Classify sources: authoritative/advisory/historical; static/daily/hourly/live; sensitive/non-sensitive; embedded/structured/mixed.

Ask: Would embedding destroy useful dates/numbers/relationships? Is this stable knowledge or current state? What proves freshness?

| Source | Authority | Changes | Sensitive? | Read as |
|---|---|---|---|---|
| current order | Authoritative | Live (as fresh as the BigQuery load) | Sensitive: customer name, address, phone, payment status | Structured |
| current inventory | Authoritative | Live | Non-sensitive | Structured |
| carrier event | Authoritative (carrier) | Live, events can arrive late | Non-sensitive (tracking data only) | Structured |
| warehouse event | Authoritative | Live | Non-sensitive | Structured |
| recent change | Authoritative (record of changes) | Hourly, as changes are made | Non-sensitive | Structured |
| runbook | Advisory | Static, new versions only | Non-sensitive | Embedded |
| historical postmortem | Historical | Static, added after incidents | Internal; customer details removed before embedding | Embedded |

**Answers:**
- **Would embedding destroy dates/numbers/relationships?** Yes for order, inventory, carrier, warehouse and change data: quantities, times and order → warehouse → SKU links would blur, so they stay structured.
- **Stable knowledge or current state?** Runbooks and postmortems are stable knowledge; everything else is current state.
- **What proves freshness?** A source time on every result (load time or event time), compared with the maximum allowed age for that source.

- **Embedded sources:** runbooks and historical postmortems, with labels (exception type, warehouse, date, version).
- **Structured/tool sources:** current order, current inventory, carrier events, warehouse events, recent changes.
- **Freshness rule:** every result carries its source time; anything older than its source's allowed age is marked stale and not used as current evidence.
- **Sensitive-data rule:** customer details stay out of the model unless needed, are masked in logs and traces, and are never embedded; tools return only the fields the investigation needs.

### Gate 2 — Chunking
| Choice | Fit | Risk |
|---|---|---|
| ~256 | precise facts/FAQ | fragmented context |
| ~512 | balanced prose | section splits |
| ~1024 | long procedures | noise/token cost |
| Structure-aware | headed docs | parser complexity |
| Parent-child | precise search + broad context | extra logic |

Ask: one paragraph or whole section? Do headings change meaning? What if size is halved/doubled? How will you measure it?

**Answers:**
- **One paragraph or whole section?** Whole section: a runbook procedure is a list of steps that only makes sense together, and each postmortem section (timeline, root cause, fix, lessons) is one chunk.
- **Do headings change meaning?** Yes: "check reservations" means different things under *Allocation failure* and *Payment hold*, so every chunk carries its document title and heading path.
- **What if size is halved/doubled?** Halved (256) splits procedures, so the agent sees half the steps; doubled (1024) mixes topics, so the right section ranks lower and costs more tokens.
- **How will you measure it?** Run the golden questions at 256 and 512 and compare: is the right section in the top 5, is any procedure split, and does the answer cite it.

- **Strategy:** structure-aware, one runbook procedure or one postmortem section per chunk.
- **Size:** about 512 tokens at most; longer sections are split at step boundaries.
- **Overlap/ancestor context:** no overlap; each chunk carries its document title and heading path.
- **Metadata:** document type, exception type, warehouse, date, version.
- **Validation experiment:** golden questions at 256 and 512; keep the smallest size that keeps procedures whole and finds the right section.
- **Measured (2026-11-23):** Layout Parser's chunk size is only a maximum: at 512 it packed each short runbook into one chunk. Splitting at the section headings (62 chunks) raised hit@1 from 0.833 to 0.917 against whole-document chunks. Every section is under 256 tokens, so 256 would not change the result.
- **Changed after the first full eval: parent-child.** Sections rank better, but the answer needs the whole procedure. In 7 of 32 cases the rule the answer needed ("only the Fulfilment duty manager can release", "do not estimate the recovery time") sat in the runbook's Escalation section, which didn't make the top 5 because questions describe the problem, not the approval chain (P01 even named the wrong owner). Now: search ranks sections, and the model gets each matching document whole (up to 4; ours are 1,000-2,000 characters). For long documents this would become "matched section + the document's Escalation section".

### Gate 3 — Embedding shape
Do not assume larger is always better. Compare at least two dimensions supported by the chosen Vertex/Gemini embedding model.

| Concern | Lower | Higher |
|---|---:|---:|
| storage/index footprint | better | worse |
| latency | often better | often worse |
| semantic capacity | lower | higher |
| fine discrimination | lower | higher |

Ask: vector count in 12 months? How similar are documents? Is bottleneck quality, footprint or latency? Which golden queries prove the choice?

```text
Model: gemini-embedding-001
Dimension A: 768
Dimension B: 3072
Golden set: the 10 exact-ID and paraphrase cases in golden_questions.jsonl + the 2 Gate 4 tests
            (python -m evals.retrieval_eval, once per table)
Quality result: identical: hit@1 0.917, hit@5 1.0, MRR 0.958 at both 768 and 3072
Latency/storage result: 62 chunks x 768 floats = ~0.4 MB vs x 3072 = ~1.5 MB; search p50 1.0 s vs 3.6 s
Final choice: 768 (same quality, smaller and ~3x faster)
```

**Answers:**
- **Vector count in 12 months?** 13 documents today; even at 200 runbooks and postmortems it is a few thousand chunks, so storage and index size don't matter at either dimension.
- **How similar are the documents?** Quite similar: several runbooks share words like "allocation", "reserved" and "warehouse", and RB-ALLOC-002 v2 and v3 are nearly the same text. Fine discrimination matters more than capacity, and the version filter (not the vector) separates v2 from v3.
- **Is the bottleneck quality, footprint or latency?** Quality. Latency is dominated by the model calls and the A2A hop, not the vector search.
- **Which golden queries prove the choice?** P01 and P05 (paraphrases next to the superseded v2), E01 and E04 (exact codes), and the scanned PM-2025-052 probe in ingest_docs.

### Gate 4 — Dense, lexical or hybrid
Dense helps paraphrases; lexical helps exact IDs/codes; hybrid handles mixed workloads; routing helps distinct query classes.

Ask: Are exact IDs common? Are paraphrases common? Which metadata filters before retrieval? Create one dense-failure and one lexical-failure query.

```text
Strategy: hybrid: a dense leg (BigQuery VECTOR_SEARCH) and a lexical leg (exact codes and IDs only); lexical runs when the question has a code
Fusion/routing: reciprocal rank fusion (k=60) of the two top-20 lists; no router (one less thing to get wrong)
Filters: register status = current, read at question time (VECTOR_SEARCH takes no JOIN, so the current versions are passed in); same embedding model and dimension;
         optional doc type, exception type, warehouse (postmortems only; runbooks apply everywhere)
Dense-failure test: "PAY-H205": a bare code; dense alone ranks RB-PAY-004 3rd, hybrid 2nd, rerank 1st
Lexical-failure test: "Units are physically there but promised to someone else's bulk order": no shared
                      words with "reservation"; dense finds RB-ALLOC-002 v3 at rank 1
Measured: the lexical leg must use exact codes only. Counting key words made hybrid worse than dense
          (hit@1 0.583 vs 0.667 without rerank); codes only made it better than both legs (0.75).
```

**Answers:**
- **Are exact IDs common?** Yes: reason codes (ALLOC-E107, PAY-H201), carrier codes (WX-HOLD), event types (SYSTEM_DOWN) and document IDs.
- **Are paraphrases common?** Yes: analysts describe symptoms ("stuck at a sorting centre because of rain"), not codes.
- **Which metadata filters before retrieval?** Current version only (from the register, not the chunk's stamped status), same embedding model and dimension; doc type, exception type and warehouse when the agent knows them.
- **Why our own lexical leg and RRF?** Both legs are plain SQL we can test and explain, and RRF needs no calibration between cosine distance and keyword counts.

### Gate 5 — Candidate count & reranking
Design `retrieve K → optional rerank → N evidence items → Gemini`.

Ask: What can small K miss? What does large K cost? Does every query need reranking? What evidence threshold causes abstention?

```text
K: 20 per leg, fused to 20 candidates
Rerank: Vertex AI Ranking API on every query (the corpus is small, so the cost is small); if it fails,
        the fused order is used and the trace says so (no silent change)
Final N: 5 evidence cards, each cut to 1,500 characters
Abstention: no candidate with a relevance score of at least 0.3 -> status no_evidence -> the agent says
            the documents don't cover it and never answers from general knowledge
Measured: rerank raises hit@1 from 0.75 to 0.917 and hit@5 from 0.917 to 1.0, for ~0.3 s per query
```

**Answers:**
- **What can small K miss?** A section both legs rank low, typically a paraphrase with a rare code in it; the reranker can't promote what it never sees.
- **What does large K cost?** Rerank latency and cost, not model tokens: N stays at 5 whatever K is.
- **Does every query need reranking?** At this size, yes. At scale, rerank only when the top fused scores are close.
- **What evidence threshold causes abstention?** Relevance below 0.3 (a starting value, tuned on the golden no-evidence questions).

### Gate 6 — Multi-agent topology
| Agent | Decision it owns | Why not a tool? | Inputs | Output contract | Independent failure? |
|---|---|---|---|---|---|
| Order Exception Orchestrator | Which checks to run, the likely cause, the outcome, when to escalate | Reasons across five sources and owns the analyst conversation | Analyst question, session state (current order, preferences) | Fixed format: OUTCOME / CAUSE / FULFILABLE, observations with evidence IDs, inference, unknown / check next | Yes: if it is down nothing answers; each tool degrades on its own |
| Fulfilment Specialist (A2A) | Can the assigned warehouse fulfil the order now (yes / no / unknown / not applicable), and why | Several steps and judgment (order line, stock, reservations, re-route options), owned and released by the fulfilment team | Order ID + forwarded correlation ID | JSON: verdict, reason, stock figures with snapshot time and freshness, reservations, alternatives, evidence IDs | Yes: separate process; the orchestrator times out at 30 s and answers partially |

**Answers:**
- **Reasoning or execution?** Both agents reason; every lookup, comparison and freshness check is code inside their tools.
- **Separate context or security?** Yes: the specialist sees stock and order lines, never customer details or payment status.
- **Different team or lifecycle?** Yes: fulfilment owns its rules and releases them separately.
- **Safe degradation if unavailable?** Yes: the orchestrator reports the evidence it has, marks fulfilment unknown and never guesses stock.

Ask: reasoning or execution? Separate context/security? Different team/lifecycle? Safe degradation if unavailable?

### Gate 7 — FunctionTool, MCP or A2A?
| Need | Starting abstraction |
|---|---|
| local deterministic operation | FunctionTool |
| standardized external capability | MCP |
| goal delegated to reasoning service | A2A |
| conventional integration | REST/gRPC |

```text
MCP boundary + reason: none in v1. Our data tools have one consumer and run in-process; A2A already shows
                       the remote boundary. If another agent needs order or inventory lookups, they become an MCP server.
A2A boundary + reason: the Fulfilment Specialist: a goal delegated to a reasoning service another team owns.
Agent Card advertises: name, description with the reply fields, endpoint, streaming, and ONE skill
                       ("fulfilment_check") with an example request. Built by hand: ADK's automatic card
                       listed every internal tool as a skill.
Remote internals opaque: instruction, tools (order line, inventory, reservations, stock elsewhere), tables, model.
Unavailable behavior: check_fulfilment returns an error result (connection refused at once, or after 30 s);
                      the answer is OUTCOME partial, "fulfilment check unavailable", no stock figure, and
                      "run the fulfilment check again" under check next.
```

The specialist is called as a tool (an AgentTool around the RemoteA2aAgent), not attached as a sub-agent as in session 19: a sub-agent takes over the conversation, and when it is down the analyst sees a raw A2A error.

### Gate 8 — Session, state & memory
| Information | Session | user: | app: | temp: | Memory | External |
|---|---:|---:|---:|---:|---:|---:|
| current case | ✓ current_order_id, current_warehouse_id | | | | | |
| preference | | ✓ answer_detail (brief / full) | | | | |
| app config | | | | | | ✓ lab.env via common/config.py |
| scratch result | | | | ✓ the harness trace, one invocation | | |
| historical conversation fact | ✓ session events, compacted every 4 turns | | | | ✗ no memory service | |
| authoritative record | | | | | | ✓ BigQuery, read live by tools |

**Answers:**
- **Survive another tab?** Yes: the same session ID in another tab sees the same investigation (SQLite-backed). A new investigation starts empty apart from user: preferences.
- **Follow the user to a new session?** Only presentation preferences (user:answer_detail). Never an order or a conclusion (SI01, SI02).
- **Authoritative data that must never become conversational memory?** Orders, inventory, carrier, warehouse and change data, and past conclusions: they are always read live.
- **Expiry and deletion?** Local: the SQLite file under output/, deleted with the demo data. Production: Vertex AI sessions with a 30-day expiry and deletion on request.

Ask: survive another tab? follow user to a new session? authoritative data that must never become conversational memory? expiry/deletion rule?

### Gate 9 — Context budget
`instructions + summary + recent turns + evidence + agent/tool outputs + answer reserve <= context`.

```text
Max evidence chunks: 5 per search, each cut to 1,500 characters
Recent-turn policy: the current turn in full, plus the last turn before it (compaction overlap 1)
Summarization trigger: every 4 turns (ADK EventsCompactionConfig, compaction_interval 4)
Answer reserve: ~2,000 tokens; a typical turn is ~10-15k tokens, far below the window, so cost and latency
                set the limit, not the context size
Never summarized: IDs, quantities, times, statuses, reason codes, evidence IDs and OUTCOME lines (the summary
                  prompt keeps them word for word), and the current turn's tool results
```

### Gate 10 — Caching
| Candidate | Example key | TTL driver | Danger |
|---|---|---|---|
| document embedding | content hash+model/version | change | stale vector |
| query embedding | query+model/version | model | privacy/cardinality |
| retrieval | query+filters+index version | corpus | stale evidence |
| tool response | args+auth scope | source | auth leakage |
| final answer | query+evidence versions | short/selective | stale answer |

Ask: What is deterministic enough to cache? What invalidates it? Must auth/tenant/user enter key? What is too risky?

```text
Cache 1 / key / TTL / invalidation: query embedding / question text + model + dimension / 30 days /
                                    a model or dimension change is part of the key
Cache 2 / key / TTL / invalidation: retrieval / question + filters + table + dimension + index version +
                                    register fingerprint / 1 day / re-ingest (index version) or ANY register
                                    status change (fingerprint, re-read every 60 s)
Cache 3 (ingest) / key / TTL:       document embedding / chunk text hash + model + dimension / 90 days
Not cached + reason: inventory and the specialist's answer (live, they decide the answer); order rows
                     (TTL 0: a fresh BigQuery read is quick); carrier, warehouse and change events (live);
                     the final answer (built on live data)
```

**Answers:**
- **What is deterministic enough to cache?** Embeddings (same text and model, same vector) and retrieval over a versioned index.
- **What invalidates it?** The model or dimension (embeddings); a re-ingest or a register change (retrieval). C02 in the golden set tests the second.
- **Must auth, tenant or user enter the key?** Not today: every analyst sees the same runbooks, and nothing user-specific is cached. If documents got per-team permissions, the access scope would join the retrieval key.
- **What is too risky?** Tool results with customer data, inventory, and final answers.

### Gate 11 — Tool/runtime policy
For tools define input/output/error contract, timeout, retry, idempotency, side-effect class and auth context.

```text
Max model calls: 8 per invocation (both services)
Max tool calls: 10
Same-tool repetition: 3 identical calls (same tool, same arguments); the 4th stops the run
Wall-clock: 90 s per invocation; the A2A call times out at 30 s (measured: 24-36 s per investigation)
Failure budget: 2 failed tool calls; the 3rd stops the run
```

All five are enforced by the harness plugin on the Runner of both services, and they block, not just record (the session 13 gap).

**Answers:**
- **What must software reject even if the model proposes it?** A tool outside the service's allowlist; a request without a correlation ID and user; malformed IDs (every tool validates its input); any write without the analyst's confirmation; a specialist reply that breaks the contract or names a different order.
- **Retryable errors?** 429, 503 and timeouts, with backoff in the cloud clients and 3 attempts on model calls. Not retryable: invalid argument, not found, policy.
- **Writes needing approval?** escalate_case, the only write: ADK tool confirmation, so nothing is saved until the analyst confirms. It is idempotent per session and order.
- **Loop termination?** Two kinds of stop. Soft (tool budget, repeated call, failures): tools are blocked and the model gets one closing call to answer from the evidence it has. Hard (model budget used, out of time, or the closing call asks for more tools): the answer is a stop message with the correlation ID. Tools stop one model call before the model budget runs out, so the last call is kept for the answer.
- **Time limits:** the 90 s budget is checked between calls; a hard 105 s deadline on the whole request stops a call that hangs and answers "partial". Every Gemini call has a 30 s timeout, BigQuery 20 s, and retries stop after 25 s in total.

Ask what software must reject even if model proposes it; retryable errors; writes needing approval; loop termination.

### Gate 12 — Grounding
Separate `OBSERVATION`, `INFERENCE`, `UNKNOWN`. Define evidence IDs, minimum synthesis evidence, conflict behavior and how historical similarity is prevented from becoming current causality.

- **Output:** a fixed format: OUTCOME / CAUSE / FULFILABLE, then OBSERVATIONS (facts with evidence IDs), INFERENCE (conclusion and why), UNKNOWN / CHECK NEXT, and HISTORY HINTS (not proof).
- **Evidence IDs:** every tool result gets one: EV-<kind>-<key>-<hash of the source time>, so the same fact at the same time always has the same ID. The harness checks that every ID in the answer was returned by a tool in that invocation; unknown IDs are shown as unverified in the UI and counted in the evals.
- **Minimum evidence for a cause:** the order plus at least one fresh, current source that confirms it (fresh inventory, a carrier exception event, an open warehouse event, a before/after pattern, the payment status). Otherwise: check next.
- **Conflict:** never pick a side; OUTCOME escalate, with an escalation draft the analyst confirms.
- **Historical similarity:** postmortem results are labelled "historical hint" by code; the agent must say whether today's data confirms or rules out the hint; a recent change becomes a cause only with the before/after pattern computed by code. The trap (S11, case A08) tests this.
- **Checked by code, not just asked for:** the answer guard compares the OUTCOME / CAUSE / FULFILABLE header with the trace before the analyst sees it. A stock claim needs a fresh, successful fulfilment check that agrees; each cause needs its own proof (the matching fulfilment reason, a consistent before/after pattern, a WX-HOLD event, an open warehouse event, a payment hold); a stopped run or a failed check becomes "partial". A correction is shown as a "CHECKED BY CODE" line. On the specialist's side, the verdict and stock numbers are set by code from its tool results; the model only explains.

### Gate 13 — Evaluation
Before UI polishing create: 10 answerable, 5 insufficient-evidence, 5 exact-ID, 5 paraphrase, 3 delegation, 2 remote-failure, 2 session-isolation and 2 stale-cache cases.

Measure retrieval quality, groundedness, citations, abstention, tool/delegation correctness, trajectory length, latency and approximate token/cost.

```text
Primary quality metric: case pass rate on the golden set (outcome, facts, documents, steps and valid
                        citations must all pass), with each check's rate reported separately
Primary operational metric: p95 latency per investigation, with average model and tool calls
Worst failure: naming a cause from stale data or from a similar postmortem (S7 / I01, S11 / A08)
Architecture change from evaluation: from offline testing: the Agent Card built by hand (opacity) and the
                                     specialist called as a tool, not a sub-agent. From the first full run:
                                     see evaluation_report.md.
```

### Gate 14 — Observability
Trace user/session/correlation ID; agents/delegation; retrieval strategy; cache hit/miss; tools proposed/executed; model/tool calls; latency; termination.

Ask: what never enters logs? what alerts? how detect MCP/A2A failure? how reproduce a bad answer?

- **Trace:** the web runtime creates a correlation ID per message and puts it in RunConfig; the A2A client forwards it as request metadata; both harnesses log under it. Each service writes one trace row per invocation: user (pseudonymous), session, tools and their outcome, evidence IDs and citations, retrieval strategy, documents and cache hit or miss, A2A outcome and latency, model and tool calls, tokens and the termination reason.
- **Never in logs:** customer name, phone and address, payment status, the analyst's email and name, the identity salt. Values are masked before they are written; the analyst appears as a salted hash.
- **Alerts (production):** share of runs not ending NORMAL, A2A timeouts and failures, citation-check failures, stale-data answers, p95 latency, 429s.
- **Detect an A2A failure:** a2a_call log rows with outcome timeout or unavailable, the specialist badge in the UI, and scripts/check_gcp.py before a demo.
- **Reproduce a bad answer:** take the correlation ID from the UI, grep both services' logs and traces, read the tool arguments, evidence IDs, retrieved documents and index version, then replay with `generate_data.py --as-of <T>`.

# Submission
Submit README, architecture, completed decision sheet, evaluation report, setup.sh, requirements, lab.env.example, code, tests/evals and sample data/instructions. Include architecture diagram, working web experience, 5-minute demo and one-page production-readiness assessment.

## Final defense
Why multi-agent? Why this retrieval? Evidence for chunk/dimension? No-evidence behavior? A2A down? State vs memory? Cache leakage/staleness? Remaining hallucination? Most expensive path? Changes for 1,000 concurrent users?

- **Why multi-agent?** Only where ownership differs: fulfilment is a separate team's judgment with its own release cycle, so it is a separate agent behind A2A. Knowledge search is a tool: it retrieves, it doesn't decide.
- **Why this retrieval?** Analysts use both exact codes and paraphrases, so hybrid with RRF, a reranker, and a current-version filter from the register at question time.
- **Evidence for chunk and dimension?** The Gate 2 and Gate 3 runs of evals/retrieval_eval.py on the golden questions (evaluation_report.md).
- **No-evidence behavior?** Search returns no_evidence below the relevance threshold; stale data is labelled stale; the answer says what to check next and who to ask.
- **A2A down?** Partial answer with the evidence that is available, "fulfilment check unavailable", no stock figures (R01, R02).
- **State vs memory?** Session state holds the current case; user: state holds presentation preferences; there is no long-term memory, so old conclusions never come back as facts.
- **Cache leakage or staleness?** Only non-personal, versioned data is cached; register changes and re-ingests change the key; live state is never cached.
- **Remaining hallucination?** Wording and inference can still be wrong. Numbers and IDs are checked (citation check, deterministic eval facts), and the fixed format keeps observation and inference apart for the analyst.
- **Most expensive path?** A cause_named investigation with a recent change: ~5-6 orchestrator model calls, the specialist's 3-4, an embedding, a rerank and ~6 BigQuery queries.
- **1,000 concurrent users?** Both services on Cloud Run with autoscaling; Vertex AI sessions; Memorystore for the caches; a BigQuery reservation or materialized views for the live tables; quota increases for Gemini; IAP sign-in; A2A over authenticated HTTPS.
