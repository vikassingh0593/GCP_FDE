# Capstone 3 — Financial Services Policy, Risk & Transaction Investigation

## Problem statement
A financial-services operations team reviews unusual business transactions and policy exceptions using current transaction/account evidence, policy manuals, approval rules, product documentation and prior cases.

Example: **Review TXN-90872. Identify applicable policy, gather current evidence, explain which conditions are satisfied or unresolved, and recommend the next review step. Do not autonomously approve or reject.**

This is a human-in-the-loop investigation assistant.

## Suggested roles
Investigation Orchestrator; Policy & Controls Specialist (RAG); Transaction Evidence Specialist (possible A2A); optional Synthesis/Critic if justified.

## Policy retrieval checkpoint
| Decision | Options | Your answer |
|---|---|---|
| Retrieval | dense / lexical / hybrid / routed | |
| Clause IDs | lexical boost / exact filter / other | |
| Policy version | effective-date filter / post-filter | |
| Jurisdiction/product | pre-filter / post-filter / both | |
| Conflict | authority ranking / newest / escalation | |

Ask whether `POL-AML-4.7` is safe with dense-only retrieval; how effective date/jurisdiction constrain evidence; what happens with two policy versions.

## Embedding checkpoint
Assume eventual millions of chunks. Record year-one vector count, clause similarity, quality-vs-footprint priority, and golden queries exposing lower-dimension degradation. Compare at least two supported dimensions.

## Trusted-context checkpoint
```text
user_id:
session_id:
current_transaction:
analyst preference:
authorization scope:
long-term memory:
```
Which are conversational convenience versus trusted enterprise identity/policy inputs?

## Authorization-aware cache checkpoint
Must analyst/tenant/auth scope be in cache keys? What if account data changes during TTL? Is policy retrieval safer to cache than transaction evidence? Should final risk conclusions be cached?

## Human boundary
```text
Agent may:
Agent may not:
Human approval required for:
Minimum evidence before recommendation:
```

## Minimum acceptance
Versioned/provenanced policy RAG; hybrid experiment; embedding-dimension experiment; multi-user/session isolation; trusted context separated from model state; authorization-aware caching; multi-agent ADK; justified A2A/MCP; explicit human boundary; observation/inference/unknown separation; conflicting-version/insufficient-evidence evaluation.

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
