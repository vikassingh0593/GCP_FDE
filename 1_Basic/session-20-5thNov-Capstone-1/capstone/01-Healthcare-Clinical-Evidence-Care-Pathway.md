# Capstone 1 — Clinical Evidence & Care Pathway Copilot

## Problem statement
A hospital group needs a clinician-facing evidence-navigation assistant spanning internal protocols, clinical guidelines, formulary documents, de-identified case summaries and operational systems.

Example: **For a de-identified patient with reduced renal function and a planned contrast-enhanced procedure, summarize applicable internal protocol, identify precaution evidence, and state what information is missing before a clinician can decide.**

The system must not diagnose or autonomously prescribe.

## Suggested roles
Clinical Case Orchestrator; Clinical Knowledge Specialist (RAG); Medication/Formulary Specialist (strong A2A candidate); deterministic patient-summary/formulary/policy tools.

## Suggested corpus
Protocols with headings/tables, formulary guidance, pathway documents, de-identified summaries, historical educational cases, and deliberately outdated/contradictory documents.

## Domain checkpoint
| Decision | Options | Your answer |
|---|---|---|
| Retrieval | dense / lexical / hybrid / routed | |
| Effective-date filter | mandatory / optional | |
| Department filter | mandatory / optional | |
| Outdated protocol | exclude / label / conditional | |
| Conflict | authority ranking / newest / human escalation | |

Ask: Do exact drug names/dosages/thresholds favor lexical retrieval? Do conceptual precaution questions favor semantic retrieval? Should outdated protocols qualify as evidence? Should patient-specific facts enter long-term conversational memory?

```text
Clinical retrieval rationale:
Privacy/memory rule:
Conflict rule:
A2A advertised skill:
A2A failure fallback:
```

## Minimum acceptance
Grounded citations/provenance; exact-term + semantic retrieval experiment; session-isolated cases; context budget; privacy-safe caching; insufficient-evidence behavior; multi-agent ADK; justified MCP/A2A; trace; outdated/conflicting-evidence evaluation.

## Architecture Decision Matrix — complete before coding

| Decision | Options to consider | Your selection | Why / evidence |
|---|---|---|---|
| UI | ADK Web / FastAPI+HTML / Streamlit / Other | | |
| Orchestration | Supervisor / Semantic router / Planner-worker / Hybrid | | |
| Agents | 2 / 3 / 4+ | | |
| Knowledge store | BigQuery / Vertex AI Vector Search / Hybrid | | |
| Retrieval | Dense / Lexical / Hybrid / Query-routed | | |
| Chunking | Fixed / Structure-aware / Parent-child / Semantic | | |
| Chunk target | 256 / 512 / 1024 tokens / Other | | |
| Embedding dimension | Lower / Medium / Higher supported dimension | | |
| Reranking | None / Top-N / Conditional | | |
| Session backend | In-memory demo / DB-backed / Vertex-managed | | |
| Long-term memory | None / ADK MemoryService / external | | |
| Context control | Top-K / token budget / summarization / hybrid | | |
| Cache | embedding / retrieval / tools / synthesis / multi-layer | | |
| MCP | None / tools / retrieval service / Other | | |
| A2A | None / one remote specialist / multiple | | |
| Failure | fail closed / partial / fallback / human escalation | | |
| Evaluation | golden Q&A / retrieval / trajectory / combined | | |
| Observability | logs / trace / correlation IDs + metrics | | |

Before locking the architecture:
1. What requires reasoning and what is deterministic software?
2. Which component deserves to be an agent rather than a tool?
3. What survives one invocation, one session, or multiple sessions?
4. What is the main correctness/latency/cost risk?

```text
Reasoning responsibilities:
Deterministic responsibilities:
Agent boundaries:
State/memory lifetimes:
Primary risk:
```

# Guided Engineering Walkthrough

### Gate 1 — Data contract
Classify sources: authoritative/advisory/historical; static/daily/hourly/live; sensitive/non-sensitive; embedded/structured/mixed.

Ask: Would embedding destroy useful dates/numbers/relationships? Is this stable knowledge or current state? What proves freshness?

```text
Embedded sources:
Structured/tool sources:
Freshness rule:
Sensitive-data rule:
```

### Gate 2 — Chunking
| Choice | Fit | Risk |
|---|---|---|
| ~256 | precise facts/FAQ | fragmented context |
| ~512 | balanced prose | section splits |
| ~1024 | long procedures | noise/token cost |
| Structure-aware | headed docs | parser complexity |
| Parent-child | precise search + broad context | extra logic |

Ask: one paragraph or whole section? Do headings change meaning? What if size is halved/doubled? How will you measure it?

```text
Strategy:
Size:
Overlap/ancestor context:
Metadata:
Validation experiment:
```

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
Model:
Dimension A:
Dimension B:
Golden set:
Quality result:
Latency/storage result:
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
