# FDE Production RAG Challenge 04 — OpsCommander

> **Participant mode:** Architecture decision + production RAG build  
> **Architecture/design time:** ~60 minutes  
> **Demo build time:** Maximum 2 hours  
> **Starting point:** Reuse the Google-native RAG code from the previous hands-on wherever appropriate.  
> **Assessment:** Decision quality, production thinking, retrieval design, and a working demonstrator.


## 1. Customer Brief & Data Landscape

OmniMart operates 2,400 stores and e-commerce. During incidents teams use runbooks, architecture docs, postmortems, chats, logs, metrics, deployment history and BigQuery order data. CTO demands Sev-1 answers in three seconds and wants auto-restart above “95% confidence.” SRE forbids uncontrolled LLM production actions.

| Source | Shape | Freshness |
|---|---|---|
| Runbook | structured doc, versions | days/weeks |
| Postmortem | narrative + timeline + tables | low |
| Architecture PDF | diagrams + text | low |
| Logs | high-volume events | seconds |
| Metrics | time series | seconds |
| Deployments | structured events | seconds |
| Orders | structured analytics | minutes |
| Incident chat | streaming narrative | seconds |

## 2. Discovery Gate

Ask 10 high-value questions about incident roles, runbook authority, stale knowledge, monitoring/deployment systems, action approval, regional boundaries, SLA, retention and current operating process. Mark three blockers.

## 3. Parsing & Data-Input Strategy

Decide which sources are parsed/chunked/embedded and which are queried live. Explain handling of architecture diagrams, postmortem timelines and runbook procedures. Do not continuously embed raw logs without defending why.

## 4. Chunking, Timeline & Overlap

| Content | Boundary | Overlap | Structural Context | Why |
|---|---|---|---|---|
| Runbook procedure | | | | |
| Warning | | | | |
| Postmortem summary | | | | |
| Timeline | | | | |
| Root cause | | | | |
| Architecture diagram | | | | |

Explain how sequence `14:30 deploy → 14:34 errors → 14:38 rollback → 14:43 recovery` survives chunking. Compare overlap with semantic-section and parent-child approaches.

## 5. Metadata, Trust & Freshness

Design metadata for service, environment, region, software version, runbook version, incident date, source authority and validity. Separate relevance, trust and freshness. The highest semantic score may be obsolete.

## 6. Retrieval Strategy

| Need | Exact | Vector | Metadata | SQL | Live API | Rerank |
|---|---:|---:|---:|---:|---:|---:|
| PAY-5037 | | | | | | |
| similar incident | | | | | | |
| 14:30 deployment | | | | | | |
| current error rate | | | | | | |
| checkout runbook | | | | | | |
| Singapore order baseline | | | | | | |

Explain why one universal retriever is inappropriate.

## 7. Multi-Source Evidence & Reranking

For “checkout failed after deployment,” combine historical incidents, current metrics, logs, deployments and runbook. Decide what can be reranked together and what remains typed evidence. Historical similarity must not be confused with current causality.

## 8. Scale & Vector Index

There are 40k curated chunks but billions of log events. Decide where BigQuery vector index helps, where it does not, and whether logs should become summarized incident/event representations before semantic retrieval.

## 9. Three-Second Latency Architecture

Build a budget for intent, static retrieval, live calls, reranking and generation. Decide conditional branches, parallel calls, caching, timeouts and progressive response. Do not execute every source sequentially.

## 10. Freshness & Stale Runbooks

Runbook v1 is semantically strongest but obsolete; v2 was published yesterday. Define candidate eligibility, ranking, cache invalidation and searchable-by SLA. Explain how the system proves that a newly approved runbook is actually retrievable.

## 11. Generation & Action Contract

Define how current evidence vs historical precedent is presented, uncertainty communicated, citations produced and unsafe remediation blocked. Explain why “95% model confidence” is not an authorization policy.

## 12. ADK Architecture

Classify `search_runbooks`, `search_incidents`, `query_logs`, `query_metrics`, `get_deployments`, `query_orders`, `create_incident_note`, `request_remediation`. Define parallel tool orchestration and deterministic approval gates.

## 13. Two-Hour Build Challenge

Create a mini corpus: current checkout runbook, obsolete runbook, two postmortems (one deceptively similar), deployment records and a small simulated metrics/orders dataset. Reuse yesterday's RAG; add metadata, exact/hybrid retrieval and simple live-data tools.

| Demo | Expected |
|---|---|
| PAY-5037 | exact identifier retrieval |
| symptom-only incident | semantic historical retrieval |
| current runbook | obsolete runbook excluded for current guidance |
| “what changed at 14:30?” | deployment tool |
| “orders down 18%” | structured/live evidence |
| restart request | no autonomous restart; approval/escalation |

ADK should choose only necessary tools and run independent evidence calls in parallel where appropriate.

## 14. Submission & Assessment

Submit architecture, static-vs-live source classification, chunking/timeline strategy, metadata, retrieval matrix, latency budget, ADK orchestration, demo output and action-safety design. Weights: discovery 10, parsing/chunking 12, source classification/retrieval 18, freshness/trust 12, scale/index 8, latency 10, ADK/action safety 12, demo 13, defense 5.

## 15. FDE Defense

Defend static vs live choices, timeline chunking, overlap, exact vs semantic retrieval, stale-source handling, vector indexing, three-second SLA, current evidence vs precedent, orchestrator responsibilities, and why confidence cannot authorize production actions.
