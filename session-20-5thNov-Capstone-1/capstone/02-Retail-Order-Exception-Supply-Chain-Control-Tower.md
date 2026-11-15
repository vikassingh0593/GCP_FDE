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
| UI | ADK Web / FastAPI+HTML / Streamlit / Other | FastAPI + HTML | ADK Web is a developer testing tool with no sign-in or custom screens; FastAPI + HTML gives a real web experience with our own API, sign-in and per-analyst sessions. ADK Web is used only for debugging. |
| Orchestration | Supervisor / Semantic router / Planner-worker / Hybrid | Supervisor | One orchestrator owns the investigation, picks the next step from the evidence, delegates fulfilment to the specialist and combines the results; limits and policy are enforced in code. |
| Agents | 2 / 3 / 4+ | 2 | Orchestrator plus the Fulfilment Specialist (A2A). Runbook and postmortem search is a tool, not an agent: it retrieves, it doesn't decide. |
| Knowledge store | BigQuery / Vertex AI Vector Search / Hybrid | BigQuery | Structured data is already in BigQuery, and its vector search handles a small runbook and postmortem set, so there is one store. Vertex AI Vector Search pays off at millions of vectors. |
| Retrieval | Dense / Lexical / Hybrid / Query-routed | Hybrid (dense + lexical) | Dense finds paraphrases ("stock held for other orders" → allocation runbook); lexical finds exact codes and IDs (warehouse IDs, exception codes). |
| Chunking | Fixed / Structure-aware / Parent-child / Semantic | Structure-aware (by section) | Runbooks and postmortems have headed sections, so one procedure or one section per chunk keeps steps together. Parent-child only if tests show sections are too long. |
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
Golden set:
Quality result: s right section on top 5 (top K)
Latency/storage result: which one is faster and what is the file s
Final choice:
```

### Gate 4 — Dense, lexical or hybrid
Dense helps paraphrases; lexical helps exact IDs/codes; hybrid handles mixed workloads; routing helps distinct query classes.

Ask: Are exact IDs common? Are paraphrases common? Which metadata filters before retrieval? Create one dense-failure and one lexical-failure query.

```text
Strategy:
Fusion/routing:
Filters:
Dense-failure test:
Lexical-failure test:
```

### Gate 5 — Candidate count & reranking
Design `retrieve K → optional rerank → N evidence items → Gemini`.

Ask: What can small K miss? What does large K cost? Does every query need reranking? What evidence threshold causes abstention?

```text
K:
Rerank:
Final N:
Abstention:
```

### Gate 6 — Multi-agent topology
| Agent | Decision it owns | Why not a tool? | Inputs | Output contract | Independent failure? |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |

Ask: reasoning or execution? Separate context/security? Different team/lifecycle? Safe degradation if unavailable?

### Gate 7 — FunctionTool, MCP or A2A?
| Need | Starting abstraction |
|---|---|
| local deterministic operation | FunctionTool |
| standardized external capability | MCP |
| goal delegated to reasoning service | A2A |
| conventional integration | REST/gRPC |

```text
MCP boundary + reason:
A2A boundary + reason:
Agent Card advertises:
Remote internals opaque:
Unavailable behavior:
```

### Gate 8 — Session, state & memory
| Information | Session | user: | app: | temp: | Memory | External |
|---|---:|---:|---:|---:|---:|---:|
| current case | | | | | | |
| preference | | | | | | |
| app config | | | | | | |
| scratch result | | | | | | |
| historical conversation fact | | | | | | |
| authoritative record | | | | | | |

Ask: survive another tab? follow user to a new session? authoritative data that must never become conversational memory? expiry/deletion rule?

### Gate 9 — Context budget
`instructions + summary + recent turns + evidence + agent/tool outputs + answer reserve <= context`.

```text
Max evidence chunks:
Recent-turn policy:
Summarization trigger:
Answer reserve:
Never summarized:
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
Cache 1 / key / TTL / invalidation:
Cache 2 / key / TTL / invalidation:
Not cached + reason:
```

### Gate 11 — Tool/runtime policy
For tools define input/output/error contract, timeout, retry, idempotency, side-effect class and auth context.

```text
Max model calls:
Max tool calls:
Same-tool repetition:
Wall-clock:
Failure budget:
```

Ask what software must reject even if model proposes it; retryable errors; writes needing approval; loop termination.

### Gate 12 — Grounding
Separate `OBSERVATION`, `INFERENCE`, `UNKNOWN`. Define evidence IDs, minimum synthesis evidence, conflict behavior and how historical similarity is prevented from becoming current causality.

### Gate 13 — Evaluation
Before UI polishing create: 10 answerable, 5 insufficient-evidence, 5 exact-ID, 5 paraphrase, 3 delegation, 2 remote-failure, 2 session-isolation and 2 stale-cache cases.

Measure retrieval quality, groundedness, citations, abstention, tool/delegation correctness, trajectory length, latency and approximate token/cost.

```text
Primary quality metric:
Primary operational metric:
Worst failure:
Architecture change from evaluation:
```

### Gate 14 — Observability
Trace user/session/correlation ID; agents/delegation; retrieval strategy; cache hit/miss; tools proposed/executed; model/tool calls; latency; termination.

Ask: what never enters logs? what alerts? how detect MCP/A2A failure? how reproduce a bad answer?

# Submission
Submit README, architecture, completed decision sheet, evaluation report, setup.sh, requirements, lab.env.example, code, tests/evals and sample data/instructions. Include architecture diagram, working web experience, 5-minute demo and one-page production-readiness assessment.

## Final defense
Why multi-agent? Why this retrieval? Evidence for chunk/dimension? No-evidence behavior? A2A down? State vs memory? Cache leakage/staleness? Remaining hallucination? Most expensive path? Changes for 1,000 concurrent users?
