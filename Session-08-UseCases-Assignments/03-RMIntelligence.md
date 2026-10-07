# FDE Production RAG Challenge 03 — RMIntelligence

> **Participant mode:** Architecture decision + production RAG build  
> **Architecture/design time:** ~60 minutes  
> **Demo build time:** Maximum 2 hours  
> **Starting point:** Reuse the Google-native RAG code from the previous hands-on wherever appropriate.  
> **Assessment:** Decision quality, production thinking, retrieval design, and a working demonstrator.


## 1. Customer Brief & Data Landscape

NorthStar Bank wants one assistant over policies, regulatory circulars, 250-page contracts, KYC documents, meeting notes, risk decisions, CRM and transaction summaries. Two users may be entitled to different evidence. Jurisdiction, effective date and purpose-limited customer access matter. Scale ranges from 18k policies and 2.5M contracts to billions of transaction summaries.

| Input | Layout/Data Problem | Critical Control |
|---|---|---|
| Policy PDF | clauses, tables, versions | jurisdiction/effective status |
| Regulatory circular | supersession, exact circular ID | authority |
| Contract PDF | clauses, definitions, schedules, cross-references | customer entitlement |
| Scanned KYC | OCR + PII | access |
| Meeting notes | noisy narrative | customer/team |
| CRM | structured | current fact |
| Transactions | high-volume structured | query, not naïve embedding |

## 2. Discovery Gate

Ask 10 high-value questions covering entitlement, purpose limitation, jurisdiction, policy authority, historical questions, customer identity, audit, external knowledge, structured analytics and decision authority. Mark three blockers.

## 3. Parsing & Contract Layout

Decide parser paths for native/scanned contracts, clause tables, amendments, signatures and structured sources. Explain what Document AI should preserve. For cross-references such as “subject to Clause 17.4,” decide whether relationships are resolved during ingestion or query time.

## 4. Chunking, Overlap & Parent-Child Retrieval

A clause may depend on definitions 100 pages earlier. Fixed overlap cannot bridge that distance.

| Content | Boundary | Overlap | Parent Context | Cross-reference Handling | Why |
|---|---|---|---|---|---|
| Definitions | | | | | |
| Clause | | | | | |
| Schedule | | | | | |
| Amendment | | | | | |
| Meeting note | | | | | |

Compare fixed overlap, clause-aware chunking, parent-child retrieval and reference expansion.

## 5. Metadata & Entitlement Controls

Design metadata for customer, deal team, classification, jurisdiction, effective date, supersession, policy status, business unit and document authority. Separate relevance fields from security fields. State which controls execute before retrieval.

## 6. Retrieval + Structured Query Strategy

| Question | RAG | Exact | SQL/Structured | Hybrid | Filter | Rerank |
|---|---:|---:|---:|---:|---:|---:|
| exact policy ID | | | | | | |
| “Can we offer X in Singapore?” | | | | | | |
| last 3 Acme meetings | | | | | | |
| current approved exposure | | | | | | |
| why exception failed | | | | | | |
| customers >₹500cr with unresolved covenant issues | | | | | | |

Explain when RAG, Text-to-SQL/structured query or both are required.

## 7. Unauthorized-but-Relevant Evidence

Another customer's risk decision is the best semantic match. Compare: retrieve then prompt-hide; retrieve then post-filter; authorization pre-filter; or another design. Explain why answer correctness is insufficient if unauthorized evidence reached model context.

## 8. Candidate/Rerank Decisions

Decide whether jurisdiction, entitlement, supersession and purpose limitation are eligibility controls or ranking signals. The Ranking API must not become an authorization engine. Define duplicate handling and Top-K/Top-N.

## 9. Scale & Indexing

Design for 100k prototype chunks, then tens of millions. Explain vector index, partitioning/filter strategy, structured-data separation and why billions of transactions should not automatically become vector chunks.

## 10. Freshness & Policy Supersession

A regulator publishes a circular at 09:00, effective immediately, superseding a differently named circular. Design detection → parse → metadata linkage → embedding → load → verification. How do you prevent the old circular from answering current-policy questions while retaining historical access?

## 11. Generation Contract

Define evidence-only answers, jurisdiction, current/historical mode, restricted evidence, citations, structured/unstructured conflicts, missing evidence and escalation to compliance.

## 12. ADK Architecture

Classify `search_policy`, `search_customer_docs`, `query_customer_data`, `compare_contract_policy`, `prepare_exception_summary`, `request_compliance_review`. Explain identity propagation to tools and why the model cannot remove entitlement filters.

## 13. Two-Hour Build Challenge

Create a small corpus: current Singapore policy, superseded policy, Acme contract with clause cross-reference, restricted BetaCorp decision, Acme meeting note, simple structured exposure table. Reuse yesterday's RAG and add metadata/filtering plus a simple structured-query tool.

| Demo | Expected |
|---|---|
| current Singapore policy | current/jurisdiction correct |
| historical policy | superseded evidence intentionally eligible |
| Acme exception reason | authorized Acme evidence |
| semantically similar BetaCorp case | excluded before model context |
| current Acme exposure | structured source, not document hallucination |
| contract clause + policy comparison | evidence from both |

ADK must route RAG vs structured vs combined requests.

## 14. Submission & Assessment

Submit architecture, contract chunking/reference strategy, entitlement metadata, retrieval matrix, structured/RAG routing, ADK design, demo outputs and audit explanation. Suggested weights: discovery 10, parsing/chunking 15, entitlement/security 20, retrieval/routing 15, freshness/versioning 10, ADK 10, demo 15, defense 5.

## 15. FDE Defense

Defend why one assistant need not mean one corpus; parser/chunking choices; cross-reference handling; pre-retrieval authorization; structured-vs-RAG routing; index strategy; supersession; orchestrator role; and what you refuse to implement merely because an executive requests it.
