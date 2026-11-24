# Architecture flows for production agentic systems

Reference architectures, each step written once:

1. **Ingestion:** turning source documents and data into knowledge the agent can use.
2. **Query runtime:** a user asks a question and the agent answers it.
   - **2a. Semantic orchestration loop:** inside Q7, when the next step depends on what was just found.
   - **2b. Session, state and memory:** how the agent remembers, in one conversation and across conversations.
   - **2c. Agent-driven UI (A2UI):** the agent shows the user a form or card instead of asking question after question.
3. **Monitoring, evaluation and release:** watching the live system, measuring quality, shipping changes safely.
4. **Action-taking agent with human approval** *(beyond the course)*: the agent changes something in another system.
5. **Multi-agent system over MCP and A2A:** agents and tools across teams and services.
6. **Security and network** *(beyond the course)*: identity, perimeter, private networking, encryption, residency.
7. **Environments and delivery** *(beyond the course, except D0)*: from a written specification and a developer's change to production.

Flows marked *beyond the course* are enterprise patterns added as a reference, not taught in the sessions.

Step names are platform-agnostic. The GCP service is in (brackets). The table under each flow lists the GCP and Databricks service for every step.

```text
   ① INGESTION ───── builds ─────► KNOWLEDGE STORES ◄──── reads ───── ② QUERY RUNTIME
        │              (indexes, facts, views, graph)                         │
        │ pipeline health                                     traces · logs   │
        └──────────────────────► ③ MONITORING, EVALUATION ◄──────────────────┘
                                     AND RELEASE
                                          │
                       tested changes released back into ① and ②
```

---

## 1. Ingestion architecture

```text
 A1 SOURCE SYSTEMS — document management system, registers, business databases
        │ new / changed / approved
        ▼
 A2 CHANGE DETECTION — event per file, scheduled sync for databases
        │   (Eventarc · Cloud Scheduler)
        ▼
 A3 LANDING STORAGE — raw, unchanged originals, versioned (Cloud Storage)
        │
        ├──────────► A4 METADATA REGISTRY SYNC — status, version, country,
        │               effective dates from the source of truth (BigQuery)
        ▼
 A5 SECURITY SCREENING — planted instructions, malicious links, personal data
        │   (Model Armor · Sensitive Data Protection)
        ▼
 A6 PARSING & OCR — layout blocks, tables, figures, reading order, pages,
        │   plus optional first-pass chunks (chunk size, ancestor headings)
        │   (Document AI Layout Parser · Enterprise Document OCR)
        │   ◄── A7 PARSE CACHE — keyed by file hash + parser version (Cloud Storage)
        ▼
 A8 QUALITY GATE — page count, OCR quality, tables intact, faithfulness
        │   (Cloud Run)              └── fail ──► QUARANTINE + human review
        ▼
 A9 CHUNKING & ENRICHMENT — your code reshapes the parser's chunks (or chunks
        │   the parsed blocks itself): tables and figures as own pieces, long
        │   pieces split, templates and copies tagged, registry metadata stamped,
        │   model-written text labelled (your code on Cloud Run · Dataflow)
        │
        ├────────────────────────────┬────────────────────────────┐
        ▼                            ▼                            ▼
 A10 EMBEDDING              A11 STRUCTURED FACTS         A12 GRAPH BUILD
   document task type,        table cells and records      entities + relations,
   cache by text + model      → facts tables               versioned ontology
   (Vertex AI embeddings)     (BigQuery)                   (Spanner Graph)
        │                            │                            │
        ▼                            ▼                            │
 A13 INDEX LOAD             A14 SERVING VIEWS &                   │
   staging + MERGE,           SEMANTIC LAYER — curated /          │
   vector + search index      authorized views, glossary,         │
   with filter columns        governed metrics                    │
   (BigQuery · Vertex AI      (BigQuery · Knowledge Catalog ·     │
    Vector Search)             Looker)                            │
        └────────────────────────────┴────────────────────────────┘
                                     ▼
 A15 VERIFY SEARCHABLE — probe query per document, table and graph (Cloud Run job)
                                     ▼
 A16 PUBLISH & RECORD — mark the version live, write pipeline health,
     alert on failure (BigQuery · Pub/Sub) ──────────────► monitoring (M1)

 Throughout: A0 PIPELINE ORCHESTRATION — one run per file, retries, dead-letter
 queue, nightly reconcile sweep (Workflows · Cloud Run jobs · Pub/Sub)
```

| Step | GCP | Databricks |
|---|---|---|
| A0 Pipeline orchestration | Workflows, Cloud Run jobs, Pub/Sub (dead-letter topic) | Lakeflow Jobs, Lakeflow Declarative Pipelines |
| A1 Source systems | Connectors / exports from the system of record | Lakeflow Connect connectors |
| A2 Change detection | Eventarc (file events), Cloud Scheduler (syncs) | Auto Loader, file-arrival job triggers |
| A3 Landing storage | Cloud Storage (versioning, retention) | Unity Catalog volumes |
| A4 Metadata registry sync | BigQuery tables + views | Delta tables in Unity Catalog |
| A5 Security screening | Model Armor (documents), Sensitive Data Protection | `ai_mask` for personal data; custom checks for planted instructions |
| A6 Parsing & OCR | Document AI Layout Parser (parsing + optional chunking), Enterprise Document OCR | `ai_parse_document` (parsing only) |
| A7 Parse cache | Cloud Storage keyed by hash + version | Auto Loader checkpoints + Delta table keyed by hash |
| A8 Quality gate | Cloud Run code, quarantine bucket, health table in BigQuery | Lakeflow Declarative Pipelines expectations |
| A9 Chunking & enrichment | Your code reshaping Layout Parser chunks, running on Cloud Run (or Dataflow for large batches) | Your Python code chunking `ai_parse_document` output (e.g. LangChain / LlamaIndex splitters) in Lakeflow pipelines |
| A10 Embedding | Vertex AI embeddings, batch prediction | Vector Search managed embeddings, Foundation Model APIs |
| A11 Structured facts | BigQuery | Delta tables |
| A12 Graph build | Spanner Graph (or Neo4j AuraDB on Google Cloud) | GraphFrames, Neo4j Spark connector |
| A13 Index load | BigQuery vector + search index, Vertex AI Vector Search | Mosaic AI Vector Search (Delta Sync index) |
| A14 Serving views & semantic layer | BigQuery authorized views, Knowledge Catalog glossary, Looker | Unity Catalog views, metric views, Genie trusted assets |
| A15 Verify searchable | Cloud Run job running probe queries | Job task running probe queries |
| A16 Publish & record | BigQuery health table, Pub/Sub notifications | Delta health table, job notifications |

**Design rules:** metadata comes from the source of truth, never from parsed text; a failed check quarantines, it never indexes silently; loads are idempotent (re-runs never duplicate); "loaded" means a real query found it.

---

## 2. Query runtime architecture (the agent)

```text
 Q1 USER CHANNEL & SIGN-IN — web or chat UI, signed-in identity
        │   (Cloud Run front end · Identity-Aware Proxy)
        ▼
 Q2 API GATEWAY — authentication, per-user quota, rate limit (Apigee)
        ▼
 Q3 REQUEST SETUP — trusted context (correlation ID, user, role, unit,
        │   geography), execution policy (budgets), request deadline
        │   (wall clock, above the run's time budget), open the trace
        │   (agent host on Agent Engine / Cloud Run)
        ▼
 Q4 INPUT SCREENING — prompt injection, jailbreak, sensitive data (Model Armor)
        ▼
 Q5 SESSION LOAD — conversation history + state; one active request per session
        │   (Agent Engine Sessions · Cloud SQL)
        ▼
 Q6 RISK CLASSIFICATION — requests that must go to a person; run by code,
        │   fail closed (Gemini classifier)     └── risky ──► H1 HAND-OFF
        ▼
 Q7 ORCHESTRATOR AGENT — answer directly · ask back · knowledge · analytics ·
        │   relationships · hand-off; several tools per turn allowed
        │   (ADK on Agent Engine · Gemini)
        ▼
 Q8 TOOL GATE (before every tool) — budgets, repeated-call fingerprint,
        │   authorization against the trusted context, argument validation
        │   (ADK before_tool callback)          └── block ──► controlled result
        ▼
 ┌────────────────────┬────────────────────┬────────────────────┬────────────────────┐
 │ K  KNOWLEDGE (RAG) │ S  ANALYTICS (SQL) │ G  RELATIONSHIPS   │ H  HAND-OFF        │
 ├────────────────────┼────────────────────┼────────────────────┼────────────────────┤
 │ K1 query embedding │ S1 metadata        │ G1 ontology        │ H1 escalation      │
 │ K2 hard filters +  │    retrieval       │    retrieval +     │    record +        │
 │    entitlements    │ S2 verified query  │    expansion       │    fixed reply     │
 │ K3 hybrid search   │    or generate SQL │ G2 generate graph  │    to the user     │
 │    (top-K)         │ S3 validate SQL    │    query           │                    │
 │ K4 rerank (top-N)  │ S4 dry run +       │ G3 check query     │                    │
 │ K5 authority order,│    cost gate       │    (read-only)     │                    │
 │    evidence cards, │ S5 bounded repair  │ G4 execute query   │                    │
 │    sufficiency     │ S6 controlled      │                    │                    │
 │    check           │    execution       │                    │                    │
 │ K6 grounded        │                    │                    │                    │
 │    generation      │                    │                    │                    │
 │ K7 verify claims,  │                    │                    │                    │
 │    one repair      │                    │                    │                    │
 └────────────────────┴────────────────────┴────────────────────┴────────────────────┘
        ▼
 Q9 RESULT HANDLING (after every tool) — success / not found / dependency /
        │   security / policy → retry · stop · continue · degrade · deny;
        │   failure budget; safe recording (ADK after_tool callback)
        │                                       └── more work ──► back to Q7
        ▼
 Q10 RESPONSE ASSEMBLY — checked text relayed word for word; sources, notes
        │   and status written by code; decision fields (outcome, cause,
        │   verdict) checked against the tool trace, unsupported values
        │   replaced, with a visible correction line (ADK after_model callback
        │   or code after the run)
        ▼
 Q11 OUTPUT SCREENING — sensitive data, unsafe content
        │   (Model Armor · Sensitive Data Protection)
        ▼
 Q12 DELIVER — stream the answer to the user (front end)
        ▼
 Q13 CLOSE REQUEST — save session, finish trace, execution report, log row
     with correlation ID (Agent Engine Sessions · Cloud Trace · Cloud Logging ·
     BigQuery) ─────────────────────────────────────────► monitoring (M1)

 Throughout: Q0 OBSERVATION — run start/end and every model and tool call
 recorded as a span with the correlation ID (ADK plugin · OpenTelemetry)
```

**Branch steps in detail**

- **K Knowledge (document RAG):**
  - K1 embed the question with the query task type;
  - K2 filters from trusted metadata and the user's entitlements, applied before the search, plus the current-version list read from the document register at question time (a superseded document can't come back, even before re-indexing);
  - K3 hybrid (meaning + words) search for the top-K candidates;
  - K4 reranking down to the top N, with a pinned ranker version (the relevance threshold was measured on it); if the ranker is down, only exact-code matches are kept, and the degraded result is never cached;
  - K5 code orders the results by authority, builds evidence cards with code-written headers, and checks whether the evidence is sufficient (abstain if not);
  - K6 the model writes JSON: answer, citations, claims;
  - K7 code checks citations, numbers and claim-to-cell values, plus a grounding score, with one repair try.
- **S Analytics (text-to-SQL):**
  - S1 retrieve catalog metadata, only when the schema doesn't fit in the prompt;
  - S2 use a verified query if one exists, otherwise the model writes the SQL;
  - S3 code check (SELECT only, allowed objects);
  - S4 dry run with a cost cap;
  - S5 bounded repair;
  - S6 run read-only on authorized views, with row and byte caps.
- **G Relationships (graph):**
  - G1 find ontology entry points by meaning, then expand them through relationships and rules (bounded);
  - G2 the model writes a read-only graph query;
  - G3 compile-only check with limits;
  - G4 execute.
- **H Hand-off:** H1 an escalation record for a person, and a fixed reply to the user.

| Step | GCP | Databricks |
|---|---|---|
| Q0 Observation | ADK plugin, OpenTelemetry → Cloud Trace | MLflow Tracing |
| Q1 User channel & sign-in | Cloud Run front end, Identity-Aware Proxy / Identity Platform | Databricks Apps (workspace sign-in) |
| Q2 API gateway | Apigee / API Gateway | AI Gateway (rate limits, usage tracking) |
| Q3 Request setup | Agent host code on Agent Engine / Cloud Run | Agent Framework code (MLflow trace request ID) |
| Q4 Input screening | Model Armor | AI Gateway guardrails |
| Q5 Session load | Agent Engine Sessions (`VertexAiSessionService`), Cloud SQL (`DatabaseSessionService`) | Lakebase (managed Postgres) |
| Q6 Risk classification | Gemini called by code | Foundation Model API called by code |
| Q7 Orchestrator agent | ADK on Agent Engine, Gemini | Agent Framework (e.g. LangGraph), Agent Bricks Supervisor Agent |
| Q8 Tool gate | ADK `before_tool` callback | Checks in agent code; Unity Catalog permissions on tools |
| K1 Query embedding | Vertex AI embeddings | Foundation Model APIs / Vector Search managed embeddings |
| K2 Hard filters + entitlements | BigQuery `WHERE`, Vertex AI Vector Search filters, row-level security | Vector Search filters, Unity Catalog row filters |
| K3 Hybrid search | BigQuery `VECTOR_SEARCH` (hybrid), Vertex AI Vector Search | Mosaic AI Vector Search hybrid query |
| K4 Rerank | Vertex AI Ranking API | Vector Search reranker |
| K5 Authority, evidence, sufficiency | Agent code | Agent code |
| K6 Grounded generation | Gemini (structured output) | Foundation Model APIs (structured outputs) |
| K7 Verify + repair | Agent code, Check Grounding API | Agent code (MLflow judges for offline evaluation) |
| S1 Metadata retrieval | Knowledge Catalog, BigQuery `VECTOR_SEARCH` | Unity Catalog metadata, metric views |
| S2 Verified query or generate | BigQuery data agents (verified queries), Gemini | Genie trusted assets, Foundation Model APIs |
| S3 Validate SQL | Agent code (e.g. sqlglot) | Agent code (e.g. sqlglot) |
| S4 Dry run + cost gate | BigQuery dry run, `maximum_bytes_billed` | `EXPLAIN` on a SQL warehouse, warehouse timeouts |
| S5 Bounded repair | Specialist agent (ADK `AgentTool`) | Agent loop with a step cap |
| S6 Controlled execution | BigQuery (read-only service account, authorized views, row-level security) | SQL warehouse (Unity Catalog grants, row filters, column masks) |
| G1 Ontology retrieval | Vertex AI embeddings + ontology store | Foundation Model APIs + ontology table |
| G2 Graph query generation | Gemini (GQL / Cypher) | Foundation Model APIs |
| G3 Query check | Spanner Graph plan / Neo4j `EXPLAIN`, read-only role | Neo4j `EXPLAIN` (external graph) |
| G4 Execute | Spanner Graph / Neo4j AuraDB | GraphFrames, Neo4j Spark connector |
| H1 Hand-off | Pub/Sub → ticketing system | Delta table + webhook to the ticketing system |
| Q9 Result handling | ADK `after_tool` callback | Agent code |
| Q10 Response assembly | ADK `after_model` callback; decision-field check in code after the run | Agent code |
| Q11 Output screening | Model Armor, Sensitive Data Protection | AI Gateway guardrails |
| Q12 Deliver | Front end (streaming) | Databricks Apps |
| Q13 Close request | Agent Engine Sessions, Cloud Trace, Cloud Logging, BigQuery | Lakebase, MLflow Tracing, inference tables |

**Design rules:**
- Identity and limits are set at Q3, before the model runs, and the model can never raise them.
- Every gate (Q8, the S3–S4 checks, G3) blocks **before** anything executes.
- The model picks the path; code decides what may answer and checks the result.
- Fields the user acts on (outcome, cause, can it ship) are set or checked by code, never taken from the model unchecked.
- Evidence a known step always needs is fetched by code, by metadata tags, not left to the model's search wording.
- A wrong route is unhelpful, never unsafe.

---

## 2a. Semantic orchestration loop

This replaces a single Q7 turn when the work is a multi-step investigation. Steps Q1–Q6 run first, and Q11–Q13 close the request.

```text
 Q1–Q6 of the query runtime
        │
        ▼
 O1 OBJECTIVE & TRUSTED CONTEXT — the case, the caller's scope, budgets
        │   (agent host on Cloud Run)
        ▼
 O2 EVIDENCE REGISTER — every result with ID, source, times, status, freshness
        │   (Firestore · Cloud SQL) ◄──────────────────────────────────────┐
        ▼                                                                  │
 O3 SEMANTIC DECISION — one next action from the allowlist, with reason,   │
        │   evidence used and confidence (Gemini structured output)        │
        ▼                                                                  │
 O4 SCHEMA VALIDATION — invented actions and bad JSON rejected (agent code)│
        ▼                                                                  │
 O5 POLICY GATE — authorization, budgets, repeats, deadline, read/write    │
        │   boundary, synthesis rules (agent code)                         │
        │        └── reject ──► recorded, the model re-plans, bounded ─────┤
        ▼ allow                                                            │
 O6 EXECUTE ONE ACTION — read tool with timeout and retry rules            │
        │   (enterprise APIs)                                              │
        ▼                                                                  │
 O7 NORMALIZE RESULT — success or a failure code; stale evidence and       │
        │   conflicts marked (agent code) ─────────────────────────────────┘
        ▼ when policy allows ending, or a budget ends the run
 O8 TERMINATION — one explicit end state: synthesize · insufficient evidence ·
        │   escalate · policy · budget · failure · timeout (agent code)
        ├── conclusion allowed ──► O9 GROUNDED SYNTHESIS — cites evidence IDs;
        │                             fact, inference, hypothesis, recommendation
        │                             (Gemini structured output)
        └── otherwise ───────────► O10 INCOMPLETE RESULT — what is missing, plus
                                      hand-off to a person (H1)

 Throughout: O0 EXECUTION TRACE — request → decision → policy → tool → evidence →
 next decision → ending, with versions (Cloud Logging · Cloud Trace · BigQuery)
```

| Step | GCP | Databricks |
|---|---|---|
| O0 Execution trace | Cloud Logging, Cloud Trace, BigQuery | MLflow Tracing, inference tables |
| O1 Objective & trusted context | Agent host code on Cloud Run | Agent Framework code on Databricks Apps |
| O2 Evidence register | Firestore / Cloud SQL | Lakebase, Delta table |
| O3 Semantic decision | Gemini `response_schema` | Foundation Model APIs (structured outputs) |
| O4 Schema validation | Agent code (Pydantic) | Agent code (Pydantic) |
| O5 Policy gate | Agent code, IAM for service permissions | Agent code, Unity Catalog permissions |
| O6 Execute one action | Enterprise APIs, Cloud Run services | Unity Catalog functions, enterprise APIs |
| O7 Normalize result | Agent code | Agent code |
| O8 Termination | Agent code | Agent code |
| O9 Grounded synthesis | Gemini `response_schema` | Foundation Model APIs (structured outputs) |
| O10 Incomplete result | Agent code, Pub/Sub → ticketing system | Agent code, webhook to the ticketing system |

**Design rules:**
- Gemini proposes; software disposes. One decision, one action, then re-evaluate.
- Identity and targets come from O1, never from model arguments.
- A conclusion needs minimum evidence by code; confidence alone never ends a run.
- Running out of budget ends in O10, and never looks like a finished result.

---

## 2b. Session, state and memory

This expands Q5 and Q13 of the query runtime.

```text
 R1 IDENTIFY USER — a stable user ID, no personal data in it
        │   (Identity-Aware Proxy for the verified identity)
        ▼
 R2 CREATE OR PICK A SESSION — scoped to that user, with starting state
        │   (Agent Engine Sessions · Cloud SQL)
        ▼
 R3 LOAD SESSION — history + session, user and app state (ADK Runner)   ◄─┐
        ▼                                                                 │
 R4 FILL INSTRUCTION — placeholders replaced from state (ADK)             │
        ▼                                                                 │
 R5 RUN THE TURN — tools write state through ToolContext (ADK · Gemini)   │
        ▼                                                                 │
 R6 SAVE EVENTS & STATE — temp: values dropped, the rest saved            │
        │   (Agent Engine Sessions · Cloud SQL) ── next message ──────────┘
        ▼ only when code calls it
 R7 SAVE TO MEMORY — add_session_to_memory (Memory Bank)
        ▼ in a later session
 R8 RECALL — the agent searches with load_memory (ADK · Memory Bank)
```

| Step | GCP | Databricks |
|---|---|---|
| R1 Identify user | Identity-Aware Proxy, Identity Platform | Databricks Apps workspace authentication |
| R2 Create or pick a session | `VertexAiSessionService`, `DatabaseSessionService` on Cloud SQL | Lakebase |
| R3 Load session | ADK Runner | Agent Framework code |
| R4 Fill instruction | ADK instruction placeholders | Agent code |
| R5 Run the turn | ADK, Gemini | Agent Framework, Foundation Model APIs |
| R6 Save events & state | Agent Engine Sessions, Cloud SQL | Lakebase |
| R7 Save to memory | `VertexAiMemoryBankService` | Agent memory in Lakebase |
| R8 Recall | `load_memory` tool, Memory Bank | Memory tool in agent code |

**Design rules:**
- Choose the store by how long a fact should live, and who should see it.
- State reaches the prompt automatically; memory has to be searched, and holds only what code saved.
- Every session lookup uses both the user and the session ID, and the user comes from the verified caller.
- Local or managed back ends are a configuration change, not an agent change.

## 2c. Agent-driven UI (A2UI)

This expands Q1 and the answer step of the query runtime, when the agent needs structured input from the user instead of a chain of chat questions.

```text
 U1 ENABLE UI FOR THE SESSION — the server switches the UI capability on for
        │   this user's session (A2UI processor store)
        ▼
 U2 DECIDE A FORM IS NEEDED — the instruction carries UI rules only when the
        │   capability is on (ADK · Gemini · A2UI instruction)
        ▼
 U3 SEND UI — the agent calls the UI tool with components from the catalog
        │   (A2UI ADK toolset)
        ▼
 U4 VALIDATE AGAINST THE CATALOG — an invalid message goes back to the agent
        │   as an error, never to the screen (A2UI processor · pinned catalog)
        ▼
 U5 RENDER — the client turns messages into native components; no HTML or
        │   script from the model (A2UI renderer)
        ▼
 U6 USER ACTS — a button sends an action with the bound form values
        ▼
 U7 VALIDATE ON THE SERVER — canonical field names, schema, business rules;
        │   field errors go back to the form (FastAPI · Pydantic)
        ▼
 U8 STORE, AUDIT, CONFIRM — only now show success; an approval stays with a
        person or a policy (BigQuery / Cloud SQL · audit log)
```

| Step | GCP | Databricks |
|---|---|---|
| U1 Enable UI for the session | `A2uiProcessorStore`, keyed by the verified user's session | Agent code with the A2UI SDK |
| U2 Decide a form is needed | ADK agent, Gemini, `A2uiInstruction` | Agent Framework, Foundation Model APIs |
| U3 Send UI | `SendA2uiToClientToolset` | Agent tool built on the A2UI SDK |
| U4 Validate against the catalog | `A2uiRequestProcessor` with a pinned catalog version | A2UI SDK processor |
| U5 Render | `@a2ui/lit` renderer on Cloud Run or Firebase Hosting | A2UI renderer in a Databricks App |
| U6 User acts | Renderer action callback → API | Databricks App front end → API |
| U7 Validate on the server | FastAPI on Cloud Run, Pydantic schemas | Databricks App back end, Pydantic schemas |
| U8 Store, audit, confirm | BigQuery or Cloud SQL, Cloud Logging audit entry | Delta table or Lakebase, audit table |

**Design rules:**
- The UI is model output: the server validates every submission, whatever the form showed.
- Components come only from a pinned catalog; the model never sends HTML or script.
- Success, validation or approval is shown only after code confirmed it.

---

## 3. Monitoring, evaluation and release architecture

```text
   INGESTION (A16)                         QUERY RUNTIME (Q0, Q13)
        │ pipeline health                        │ traces · logs · reports
        └───────────────────┬────────────────────┘
                            ▼
 M1 TELEMETRY CAPTURE — spans, structured logs, execution reports, pipeline
        │   health, all keyed by correlation ID (Cloud Trace · Cloud Logging · BigQuery)
        ▼
 M2 LOG ROUTING & RETENTION — sinks, personal data masked, retention rules,
        │   audit logs (log sinks · Cloud Audit Logs · Sensitive Data Protection)
        │
        ├──────────────── LIVE LOOP ────────────────┐
        ▼                                           ▼
 M3 METRICS — latency p50/p95, block and      M6 QUALITY SAMPLING — sampled live
    escalation rates, budget hits, 429s,         answers scored by a judge model,
    cost per task, freshness                     plus a human review queue
    (Cloud Monitoring)                           (Gen AI evaluation service)
        ▼                                           ▼
 M4 DASHBOARDS (Looker Studio)                M7 FEEDBACK CAPTURE — user ratings and
        ▼                                        expert labels become test cases
 M5 ALERTS & ON-CALL                             (BigQuery)
    (Cloud Monitoring alerting)                     │
                                                    ▼
 ─────────────────────────────── RELEASE LOOP ───────────────────────────────
 M8 TEST ASSETS — golden set, adversarial and runtime tests, recorded responses
        │   (Cloud Storage · BigQuery)
        ▼
 M9 OFFLINE EVALUATION — scored per stage: retrieval, answer, routing, safety,
        │   latency, cost (Gen AI evaluation service · adk eval)
        ▼
 M10 RELEASE GATE — any change (code, prompt, model, rules, corpus, index,
        │   policy) must pass before release (Cloud Build)
        ▼
 M11 VERSIONED ROLLOUT — app + prompt + model + knowledge + tools + policy
        │   versions; canary, traffic split, rollback
        │   (Artifact Registry · Cloud Deploy · Cloud Run revisions)
        ▼
     released into ingestion (①) and the query runtime (②)

 Over time: M12 LIFECYCLE WATCH — model retirement dates, parser and embedding
 version changes (blue/green re-index), data drift (Cloud Scheduler checks)
 M13 COST & CAPACITY — budgets, quotas, reserved model capacity
 (Cloud Billing budgets · Provisioned Throughput)
```

| Step | GCP | Databricks |
|---|---|---|
| M1 Telemetry capture | Cloud Trace (OpenTelemetry), Cloud Logging, BigQuery | MLflow Tracing, inference tables, system tables |
| M2 Log routing & retention | Log sinks, Cloud Audit Logs, Sensitive Data Protection | Audit system tables, Delta retention, `ai_mask` |
| M3 Metrics | Cloud Monitoring, BigQuery scheduled queries | Lakehouse Monitoring, SQL queries on system tables |
| M4 Dashboards | Looker Studio / Looker | AI/BI dashboards |
| M5 Alerts & on-call | Cloud Monitoring alerting | SQL alerts, job notifications |
| M6 Quality sampling | Gen AI evaluation service, review queue | MLflow 3 production monitoring (judges), Review App |
| M7 Feedback capture | BigQuery | Feedback stored on MLflow traces, Review App |
| M8 Test assets | Cloud Storage, BigQuery | MLflow evaluation datasets |
| M9 Offline evaluation | Gen AI evaluation service, `adk eval` | `mlflow.genai.evaluate` |
| M10 Release gate | Cloud Build | Databricks Asset Bundles in CI |
| M11 Versioned rollout | Artifact Registry, Cloud Deploy, Cloud Run revisions (traffic split) | Unity Catalog model / prompt registry, Model Serving traffic split, Databricks Apps deployments |
| M12 Lifecycle watch | Cloud Scheduler checks, model lifecycle notices | Scheduled jobs, system tables |
| M13 Cost & capacity | Cloud Billing budgets, Provisioned Throughput | Billing system tables, budgets, provisioned throughput endpoints |

**Design rules:** one correlation ID links every record of a request; logs hold decisions and references, never raw personal data; nothing reaches users without passing the release gate; every live failure becomes a new test case.

---

## 4. Action-taking agent with human approval · BEYOND THE COURSE

Steps Q1–Q8 of the query runtime run first (sign-in, request setup, screening, orchestrator, tool gate). This flow starts when the agent decides that something must be **changed**.

```text
 Q1–Q8 of the query runtime → the agent decides an action is needed
        │
        ▼
 C1 PROPOSE ACTION — structured proposal: what, which target, why, evidence;
        │   no side effects yet (ADK tool that returns a proposal)
        ▼
 C2 POLICY CHECK — is this action allowed for this user, role and target?
        │   risk tier: never / needs approval / automatic (policy code · IAM)
        │        ├── never ───────────────────────► refuse and explain
        │        └── low risk, clear-cut ─────────► C5 (auto-approved, audited)
        ▼
 C3 APPROVAL REQUEST — proposal + evidence sent to the approver
        │   (ADK tool confirmation · Workflows callback · ticketing system)
        ▼
 C4 DURABLE WAIT — state saved; resumes on the decision, expires or escalates
        │   on timeout (Workflows · Firestore · Agent Engine Sessions)
        │        └── rejected or expired ─────────► inform the user, close
        ▼
 C5 EXECUTE — separate least-privilege service, idempotency key, dry run
        │   first where supported (Cloud Run service · target system API)
        ▼
 C6 VERIFY — read the target system back to confirm the change
        │        └── mismatch ────────────────────► C9 UNDO + alert
        ▼
 C7 AUDIT RECORD — proposer, approver, before / after, policy version,
        │   correlation ID (BigQuery · Cloud Audit Logs)
        ▼
 C8 NOTIFY — requester and system owner (Pub/Sub · email / chat)

 Within the undo window: C9 UNDO / COMPENSATE — the defined reverse step,
 itself approved and audited (same execution service)
```

| Step | GCP | Databricks |
|---|---|---|
| C1 Propose action | ADK function tool that returns a proposal | Agent Framework tool that returns a proposal |
| C2 Policy check | Policy code, IAM Conditions | Policy code, Unity Catalog function permissions |
| C3 Approval request | ADK tool confirmation, Workflows callback endpoint, Pub/Sub → ticketing system | Databricks Apps approval screen, webhook to the ticketing system |
| C4 Durable wait | Workflows, Firestore / Cloud SQL, Agent Engine Sessions | LangGraph checkpoints in Lakebase, Lakeflow Jobs |
| C5 Execute | Cloud Run service with its own service account, Cloud Tasks for retries | Lakeflow Job or Unity Catalog function run by a service principal |
| C6 Verify | Read tool against the target system | Read tool against the target system |
| C7 Audit record | BigQuery audit table, Cloud Audit Logs | Delta audit table, audit system tables |
| C8 Notify | Pub/Sub → email / chat | Job notifications, webhook |
| C9 Undo / compensate | Reverse operation on the same Cloud Run service | Reverse operation on the same job or function |

**Design rules:**
- The model proposes, a person or a policy approves, a separate service executes.
- Every action is idempotent, verified, audited and reversible.
- The approval wait is durable: nothing is lost if the system restarts.

---

## 5. Multi-agent system over MCP and A2A

Steps Q1–Q6 of the query runtime (identity, context, screening, session) run first, and Q9–Q13 close the request.

```text
 Q1–Q6 of the query runtime
        │
        ▼
 N1 ORCHESTRATOR AGENT — answers general turns itself, delegates only
        │   the work a specialist owns, picks tools
        │   (ADK on Agent Engine · Gemini)
        ├───────────────────────────────┐
        ▼                               ▼
 N2 AGENT DISCOVERY               N5 TOOL ACCESS OVER MCP — business
    card URLs from configuration,    functions on MCP servers (data,
    checked against an allowlist;    APIs); the agent discovers them
    each Agent Card at               at run time and sees only the
    /.well-known/agent-card.json     tools it is allowed; each server
    gives name, skills and           authorizes the user's call
    endpoint (fetched by ADK         (ADK McpToolset · FastMCP · MCP
    RemoteA2aAgent)                  Toolbox for Databases · Cloud Run)
        │                               │
        ▼                               │
 N3 DELEGATION OVER A2A — task          │
    sent with the user's identity       │
    and correlation ID, under a         │
    timeout (ADK RemoteA2aAgent)        │
        │                               │
        ▼                               │
 N4 REMOTE AGENT — its own              │
    instruction, tools and runtime      │
    controls, hidden from the caller;   │
    its reply's decision fields set by  │
    code from its tool results;         │
    may ask back (input-required)       │
    (ADK to_a2a · Agent Engine ·        │
    Cloud Run)                          │
        └───────────────┬───────────────┘
                        ▼
 N6 RESULT AGGREGATION — merge, resolve conflicts, keep citations and
        │   which agent produced what; a remote agent that failed or
        │   timed out becomes "unavailable", and the answer is marked
        │   partial (orchestrator)
        ▼
 Q9–Q13 of the query runtime

 Throughout:
 N7 IDENTITY PROPAGATION — the user's token + correlation ID on every hop;
    no shared admin credential (OAuth · Workload Identity)
 N8 CROSS-AGENT TRACING — one trace across all agents and servers; the
    correlation ID rides in A2A request metadata and MCP headers
    (OpenTelemetry context propagation · Cloud Trace)
 N9 GOVERNANCE — allowlists, pinned versions, contract tests for every
    remote agent and MCP server (Git · Cloud Build)
```

| Step | GCP | Databricks |
|---|---|---|
| N1 Orchestrator agent | ADK on Agent Engine, Gemini | Agent Framework, Agent Bricks Supervisor Agent |
| N2 Agent discovery | Card URLs in configuration with an allowlist; Agent Card at `/.well-known/agent-card.json`, fetched by `RemoteA2aAgent` | Allowlist of serving endpoints and Apps |
| N3 Delegation over A2A | ADK `RemoteA2aAgent`, as a sub-agent or inside `AgentTool`, with `timeout` and `a2a_request_meta_provider` | Calls to agent serving endpoints (check current A2A support) |
| N4 Remote agent | ADK `to_a2a()` app on Cloud Run, or Agent Engine, each with its own runtime controls | Model Serving or Databricks Apps |
| N5 Tool access over MCP | ADK `McpToolset` with `tool_filter`, MCP servers built with FastMCP on Cloud Run, MCP Toolbox for Databases | Managed MCP servers (UC functions, Genie, Vector Search), custom MCP servers on Apps |
| N6 Result aggregation | Orchestrator code | Orchestrator code |
| N7 Identity propagation | OAuth tokens, Workload Identity | On-behalf-of-user authentication, service principals |
| N8 Cross-agent tracing | OpenTelemetry → Cloud Trace; correlation ID in A2A metadata and MCP headers | MLflow Tracing |
| N9 Governance | Configuration in Git, contract tests in Cloud Build | Asset Bundles, tests in CI |

**Design rules:**
- MCP connects agents to tools; A2A connects agents to agents.
- A fixed lookup stays a tool (function or MCP). Delegate over A2A only when the work needs its own reasoning, owner or release cycle.
- A remote agent being down is a normal outcome. Test it by stopping the remote: the user gets "unavailable" and the evidence so far, never invented specialist facts.
- The Agent Card is public: it should carry the real URL and only the skills callers need.
- The remote agent's verdict and numbers come from its tools, written by its code; the caller still checks the reply's evidence IDs, because nothing crossing A2A is trusted as known.
- Every boundary authorizes the **user**, not a shared service account.
- Remote agents and MCP servers are reviewed and pinned like any dependency.

---

## 6. Security and network architecture · BEYOND THE COURSE

Content screening (Model Armor, Sensitive Data Protection) stays in the query runtime (Q4, Q11). This flow is the platform underneath.

```text
   Users                                          Admins / CI
     │ P1 SSO + MFA                                 │ P1
     ▼                                              ▼
 P2 EDGE — WAF, DDoS protection, TLS (Cloud Armor · external load balancer)
     ▼
 P3 ACCESS PROXY — only signed-in, authorized users reach the app
     │   (Identity-Aware Proxy)
     ▼
 ┌── P4 DATA PERIMETER (VPC Service Controls) ───────────────────────────────┐
 │ P5 PRIVATE NETWORK — services and Google APIs on private addresses        │
 │    (VPC · Private Service Connect · Private Google Access)                │
 │                                                                           │
 │    front end ─► agent runtime ─► tools ─► data stores · model endpoints   │
 │    each component runs as its own P6 SERVICE IDENTITY                     │
 │    (one service account each, least privilege, no keys)                   │
 │                                                                           │
 │ P7 ENCRYPTION — customer-managed keys at rest, TLS in transit (Cloud KMS) │
 │ P8 SECRETS — never in code or images (Secret Manager)                     │
 │ P9 TENANT ISOLATION — silo: a project per tenant; or pool: tenant ID on   │
 │    every row, row-level security, tenant filters, per-tenant cache keys   │
 └───────────────────────────────────────────────────────────────────────────┘
     │
 P10 RESIDENCY & ORG POLICY — allowed regions, regulated workloads
     (Organization Policy · Assured Workloads)
 P11 AUDIT & DETECTION — admin and data-access logs, misconfiguration and
     threat detection (Cloud Audit Logs · Security Command Center)
```

| Step | GCP | Databricks |
|---|---|---|
| P1 User identity | Cloud Identity, Workforce Identity Federation (external identity provider) | Workspace SSO with your identity provider, SCIM provisioning |
| P2 Edge | Cloud Armor, external Application Load Balancer | IP access lists, front-end Private Link |
| P3 Access proxy | Identity-Aware Proxy | Databricks Apps workspace authentication |
| P4 Data perimeter | VPC Service Controls | Private Link, serverless egress controls |
| P5 Private network | VPC, Private Service Connect, Private Google Access | Private Link, customer-managed VPC / VNet |
| P6 Service identity | Service accounts, Workload Identity | Service principals |
| P7 Encryption | Cloud KMS (customer-managed keys) | Customer-managed keys |
| P8 Secrets | Secret Manager | Secret scopes |
| P9 Tenant isolation | Project or dataset per tenant, or BigQuery row-level security + tenant filters | Catalog per tenant, or row filters + tenant filters |
| P10 Residency & org policy | Organization Policy (resource locations), Assured Workloads | Workspace region, compliance security profile |
| P11 Audit & detection | Cloud Audit Logs, Security Command Center | Audit log system tables, security monitoring |

**Design rules:**
- No public path to data: private networking inside a perimeter.
- Every component has its own identity with the least privilege.
- Residency applies to every service, the model endpoint included.
- Tenant isolation covers indexes, caches and logs too.

---

## 7. Environments and delivery · BEYOND THE COURSE

Evaluation and rollout reuse the release loop of architecture 3 (M9–M11).

```text
 D0 SPECIFICATION — constitution, spec with requirement IDs, plan and tasks,
        │   analyzed for gaps before code; a change starts at the earliest
        │   affected document (Spec Kit · coding agent)
        ▼
 D1 SOURCE CONTROL — code, prompts, policies, evaluation sets and
        │   infrastructure in Git (GitHub / GitLab via Developer Connect)
        ▼ pull request + review
 D2 BUILD — pinned dependencies, container image, vulnerability scan, signing
        │   (Cloud Build · Artifact Registry · Artifact Analysis)
        ▼
 D3 INFRASTRUCTURE AS CODE — the same definitions for every environment
        │   (Terraform · Infrastructure Manager)
        ▼
 D4 DEV ENVIRONMENT — own project, synthetic or masked data
        ▼
 D5 TEST ENVIRONMENT — integration tests + offline evaluation and release
        │   gate (M9–M10)
        ▼
 D6 STAGING — production-like configuration, shadow traffic, load test
        ▼
 D7 PROMOTION — the same signed artifact moves on; approval for production
        │   (Cloud Deploy · Binary Authorization)
        ▼
 D8 PRODUCTION ROLLOUT — canary, traffic split, monitored (M11, M1–M5)

 Across all environments:
 D9 CONFIG & SECRETS PER ENVIRONMENT — models, thresholds and endpoints in
    configuration; secrets per environment (Secret Manager)
 D10 ROLLBACK — the previous revision together with its prompt and index
     version (Cloud Run revisions · versioned indexes)
```

| Step | GCP | Databricks |
|---|---|---|
| D0 Specification | Spec Kit with Gemini CLI or Claude Code, documents in Git | Spec Kit with Databricks Git folders |
| D1 Source control | GitHub / GitLab via Developer Connect | Git folders with GitHub / GitLab |
| D2 Build | Cloud Build, Artifact Registry, Artifact Analysis | CI runner (e.g. GitHub Actions) building Asset Bundles |
| D3 Infrastructure as code | Terraform, Infrastructure Manager | Terraform provider, Asset Bundles |
| D4 Dev environment | Separate dev project | Dev workspace or catalog |
| D5 Test environment | Test project, Cloud Build test stage | Test workspace, bundle deploy + `mlflow.genai.evaluate` |
| D6 Staging | Staging project, tagged Cloud Run revision for shadow traffic | Staging workspace |
| D7 Promotion | Cloud Deploy, Binary Authorization | Bundle promotion, Unity Catalog model alias change |
| D8 Production rollout | Cloud Deploy canary, Cloud Run traffic split | Model Serving traffic split, Apps deployment |
| D9 Config & secrets per environment | Secret Manager, environment variables per revision | Secret scopes, bundle targets |
| D10 Rollback | Cloud Run revisions, versioned prompts and indexes | Unity Catalog model versions and aliases, Delta time travel |

**Design rules:**
- Specification first: requirements, plan and tasks are reviewed before code, and generated documents are not proof; executed tests are.
- Build once, promote the same signed artifact.
- A prompt, policy or index change is a release and passes the same gates as code.
- Rollback restores code, prompt and index versions together.
