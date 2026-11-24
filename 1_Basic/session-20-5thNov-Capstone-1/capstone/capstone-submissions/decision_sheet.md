# Decision sheet

> Code paths on this page are relative to [`retail-control-tower/`](retail-control-tower/).

The completed decision matrix, with where each decision lives in the code and what proves it. The reasoning for each choice is in the capstone design doc ([matrix and Gates 1–14](../02-Retail-Order-Exception-Supply-Chain-Control-Tower.md)); measured results are in [evaluation_report.md](evaluation_report.md).

**Evidence status:** ✅ proven by offline tests · 📏 measured by the evals (needs a GCP run) · 📝 design only.

| Decision | Selection | Where in the code | Evidence |
|---|---|---|---|
| UI | FastAPI + HTML, training sign-in, per-analyst sessions | `web/`, `orchestrator/identity.py` | ✅ `test_api_offline.py` (pseudonymous ID, isolation 404) |
| Orchestration | Supervisor: one orchestrator chooses checks from the order | `orchestrator/order_exception_agent/agent.py` | 📏 trajectory checks (`expected_steps`, `forbidden_steps`) |
| Agents | 2: orchestrator + Fulfilment Specialist (A2A); search is a tool | `orchestrator/`, `fulfilment_specialist/` | ✅ `test_a2a_offline.py` (specialist imports nothing from the orchestrator) |
| Knowledge store | BigQuery (tables, chunks and vectors in one place) | `scripts/ingest_docs.py`, `orchestrator/retrieval/search.py` | 📏 ingest probes |
| Retrieval | Hybrid: dense + lexical, RRF (k=60), lexical = exact codes only; current versions from the register | `search.py` | ✅ `test_retrieval_offline.py` · 📏 `evals/retrieval_eval.py --legs` |
| Chunking | Sections for search (Layout Parser + split at `##`), whole document for the answer (parent-child) | `ingest_docs.py` step 7; `search.to_cards()` | ✅ ingest and retrieval tests · 📏 Gate 2 run (sections 0.917 vs whole docs 0.833 hit@1) and eval run 1 (7 cases missing Escalation rules) |
| Chunk target | 512 tokens; compare with 256 | `CHUNK_SIZE`, `--chunk-size` | 📏 Gate 2 run |
| Embedding dimension | 768; compare with 3072 | `EMBEDDING_DIMENSION`, `--dimension` | 📏 Gate 3 run |
| Reranking | Top-N: Ranking API, K=20 → N=5, abstain below 0.3 | `search.rerank()`, `MIN_RELEVANCE_SCORE` | ✅ abstention test · 📏 `--no-rerank` run |
| Session backend | DB-backed (ADK DatabaseSessionService, SQLite); Vertex as the production step | `orchestrator/sessions.py` | ✅ session state test |
| Long-term memory | None; presentation preferences in `user:` state | `orchestrator/tools/preferences.py` | 📏 SI01, SI02 |
| Context control | Hybrid: top 5 chunks cut to 1,500 chars, compaction every 4 turns, IDs kept word for word | `agent.py` (EventsCompactionConfig), `search.CONTENT_CHARS` | 📝 |
| Cache | Multi-layer: query embedding 30 d, retrieval 1 d keyed on index version + register fingerprint, document embeddings 90 d; inventory, orders and answers never | `orchestrator/retrieval/cache.py`, `embeddings.py`, `search.py` | ✅ register change → cache miss · 📏 C01, C02 |
| MCP | None in v1 | — | 📝 |
| A2A | One remote specialist, called as a tool; hand-built Agent Card with one skill | `orchestrator/a2a_client.py`, `fulfilment_specialist/fulfilment_agent/card.py` | ✅ card opacity test, contract parsing, correlation forwarding |
| Failure | Partial + human escalation (confirmed); fail closed without context; no silent fallback | `a2a_client.py`, `tools/escalation.py`, `common/harness/plugin.py` | ✅ dead specialist → partial; declined escalation writes nothing · 📏 R01, R02 |
| Evaluation | Combined: golden Q&A, retrieval, trajectory, citations | `evals/` | ✅ `test_eval_scoring.py` · 📏 full run |
| Observability | Correlation ID across both services, masked logs, trace row per invocation | `common/harness/` | ✅ trace and refusal tests |

## Limits enforced in code (Gate 11)

| Limit | Value | Enforced by |
|---|---|---|
| Model calls per invocation | 8; tools stop after call 7 so call 8 writes the answer | harness `before_model_callback`, `before_tool_callback` |
| Tool calls per invocation | 10 | harness `before_tool_callback` |
| Identical tool calls | 3 (4th: soft stop, one closing call) | harness fingerprint |
| Failed tool calls | 2 (3rd: soft stop, one closing call) | harness `after_tool_callback` |
| Wall clock | 90 s (hard stop, checked between calls); A2A call 30 s, BigQuery 30 s (measured: investigation 24–36 s, A2A 9–15 s) | harness; `a2a_client.py`; `clients.py` |
| Freshness | orders and inventory 300 min (demo setting) | `common/freshness.py` |

## Changed during the build

| Was | Now | Why |
|---|---|---|
| Specialist as a sub-agent (s19) | Specialist as a tool (`AgentTool` around `RemoteA2aAgent`) | A sub-agent takes over the conversation; a dead specialist surfaced as a raw error |
| ADK's automatic Agent Card | Hand-built card, one skill | The automatic card listed every internal tool (opacity) |
| ADK Web for debugging | Terminal runner (`orchestrator/cli.py`) | ADK Web sends no correlation ID, so the harness refuses it (fail closed) |
| Budgets 6 model / 8 tool calls | 8 / 10 | The S6 path needs 5–6 model calls and 5 tools |
| Markdown runbooks | PDFs + document register + Document AI | Matches the enterprise source (and session 8) |
| Tools ran on the event loop | Orchestrator tools in ADK's tool thread pool; specialist tools async (BigQuery in a worker thread) | One slow query froze every analyst's request and the specialist's Agent Card |
| Specialist's structured reply unchecked | Its harness checks the reply's evidence_ids like a text citation | An invented ID could cross A2A as "known" evidence |
| Stop = no more model calls | Soft stop (one closing call) vs hard stop; last model call kept for the answer | A stopped run returned only a stop message, never an answer |
| One section per evidence card | Whole document per card (parent-child) | Eval run 1: the decision rules were in the Escalation section, which rarely ranked; P01 named the wrong owner |
| Lexical leg: codes + key words | Codes and IDs only | Key words made hybrid worse than dense alone (Gate 4 run) |
| Header values listed, not defined | One-line meaning per value; "partial" only when a tool failed | Eval run 1: partial vs check_next mixed up; "stock is there" said while the specialist was down |
| The model decides the header | Code checks it against the trace (answer guard) and corrects unsupported claims | External review: the values the analyst acts on had no code check |
| The specialist's model copies the verdict and numbers | Code sets them from the specialist's tool results; invented IDs can't cross A2A | External review blocker #1 |
| API trusted the analyst ID in the request | Signed, expiring analyst token on every call | External review: the ID appears in logs |
| No overall deadline | Gemini timeout, retry cap, 105 s request deadline | External review: one hung call had no limit |
| Eval reported, never failed | Per-check thresholds; exit code 1 below them | External review: nothing could block a bad change |
| `semantic-ranker-default@latest` | Pinned `semantic-ranker-default-005` | `@latest` can change without a code change; the threshold was measured on -005 |
| Model temperature unset (Gemini 3 default 1.0) | 0 for both agents (`MODEL_TEMPERATURE`) | Measured on the golden set: t = 0 better on cause, outcome, fulfilable, facts and steps, and faster at p95 (22 s vs 31 s) |
| The model searched for the change runbook itself | The before/after comparison fetches it in code, by register tags (runbook, recent_change), never by ID | Eval run 5: the model reworded its query and missed RB-CHG-006 in A06 and A07 |
| ADK's bare "This tool call is rejected." after a declined escalation | `explain_decline` callback: "declined by the analyst, nothing saved, not a failure" | Live web check: the model said "could not be saved at this time" and dropped its headings |
