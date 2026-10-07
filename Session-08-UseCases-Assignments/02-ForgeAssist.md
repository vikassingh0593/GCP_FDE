# FDE Production RAG Challenge 02 — ForgeAssist

> **Participant mode:** Architecture decision + production RAG build  
> **Architecture/design time:** ~60 minutes  
> **Demo build time:** Maximum 2 hours  
> **Starting point:** Reuse the Google-native RAG code from the previous hands-on wherever appropriate.  
> **Assessment:** Decision quality, production thinking, retrieval design, and a working demonstrator.


## 1. Customer Brief & Data Landscape

TitanForge's 4,800 technicians maintain compressors and turbines. Inputs include 800-page manuals, safety bulletins, exploded diagrams, scanned service sheets, parts XLSX/CSV, technician notes, service tickets and live telemetry. Exact identifiers such as `E117`, `E171`, `ZX-440`, `ZX-440A` and serial ranges are safety-critical. Technician notes are useful but non-authoritative. Safety bulletins outrank manuals. 20% of sites have unstable connectivity. P95 answer target is 2 seconds.

| Input | Structural Problem | Freshness |
|---|---|---|
| Service manual PDF | procedures + warnings + diagrams + tables | quarterly |
| Safety bulletin | serial applicability + urgent warning | <15 min |
| Scanned worksheet | handwriting/stamps | irregular |
| Parts catalog | exact part/model compatibility | weekly |
| Technician notes | noisy, useful, unsafe shortcuts possible | continuous |
| Service tickets | semi-structured histories | continuous |
| Telemetry | time series | seconds |
| Equipment master | model/serial/configuration | transactional |

## 2. Discovery Gate

Write 10 high-value questions covering source authority, serial/model hierarchy, safety precedence, offline meaning, telemetry freshness, action authority, languages, image requirements, SLA and acceptable failure. Mark three blockers.

## 3. Parsing & Multimodal Layout

| Input | Parser/Method | Preserve | Failure Mode | Fallback |
|---|---|---|---|---|
| 800-page manual | | | | |
| Diagram + callouts | | | | |
| Troubleshooting tree | | | | |
| Parts table | | | | |
| Scanned sheet | | | | |
| Technician note | | | | |
| Photo of assembly | | | | |

Explain how warnings remain attached to procedures, diagram labels remain associated with figures, and multi-page parts tables retain headers. Decide where Document AI Layout Parser is sufficient and where OCR/vision/structured ingestion is needed.

## 4. Chunking & Overlap

Design different chunk policies for procedure steps, warnings, diagrams/captions, troubleshooting trees, parts tables and service cases.

| Content | Boundary | Size | Overlap | Parent/Neighbor Expansion | Why |
|---|---|---:|---:|---|---|
| Procedure | | | | | |
| Safety warning | | | | | |
| Troubleshooting tree | | | | | |
| Parts table | | | | | |
| Diagram/caption | | | | | |
| Service case | | | | | |

Explain why a warning separated from its procedure is dangerous. Decide whether overlap or parent-child retrieval is safer.

## 5. Metadata & Authority

Design metadata for model, variant, serial range, document authority, effective date, safety level, language, source type and part number. Classify hard filters vs ranking signals.

## 6. Retrieval Strategy

| Need | Exact | Vector | Metadata | Structured/Live | Hybrid | Rerank |
|---|---:|---:|---:|---:|---:|---:|
| Error E117 | | | | | | |
| “pressure fluctuates after sensor replacement” | | | | | | |
| TF-99318 valve compatibility | | | | | | |
| latest ZX-440 safety bulletin | | | | | | |
| similar repair cases | | | | | | |
| current vibration | | | | | | |

Explain why semantic similarity between E117 and E171 is not acceptable evidence.

## 7. Authority Conflict & Reranking

Candidates contain: technician note “bypass interlock”; manual “never bypass”; today's bulletin “TF-99000–TF-99500 must shut down.” Machine = TF-99318. Decide what is filtered, boosted, retained for context and escalated. Ranking score must not override safety authority.

## 8. Scale, Index & Latency

Corpus grows from 80k to 5M chunks. Decide exact vector search vs index, hybrid search, candidate K and rerank N. Prototype timings: embedding 180ms, retrieval 400ms, rerank 650ms, telemetry 500ms, generation 1400ms. Build a <2s strategy using conditional execution, parallelism, caching or SLA renegotiation.

## 9. Freshness & Offline Contradiction

Safety bulletins must be searchable within 15 minutes, yet remote sites may be offline. “Fully offline and always latest” cannot always both hold. Offer three product/architecture compromises and state the business risk of each.

## 10. Generation & Safety Contract

Define grounding, citations, model/serial applicability, conflicting evidence, unsafe technician notes, missing telemetry, abstention and action boundaries.

## 11. ADK Architecture

Classify `knowledge_search`, `equipment_lookup`, `telemetry`, `identify_part`, `create_ticket`, `order_part`, `shutdown_review` as tools/agents/deterministic services. Define orchestrator responsibilities and approval gates. Avoid agent proliferation unless justified.

## 12. Architecture Submission

Show source-specific ingestion plus online paths for exact/hybrid knowledge retrieval and live telemetry. Name Google services and deterministic safety controls.

## 13. Two-Hour Build Challenge

Reuse yesterday's RAG. Create a mini corpus: ZX-440 manual, conflicting technician note, latest safety bulletin applying to TF-99318, parts table, one historical ticket. Implement metadata and exact+semantic retrieval. ADK routes knowledge vs equipment/telemetry-style requests.

| Demo | Expected |
|---|---|
| “What is E117?” | exact identifier evidence |
| symptom description without code | semantic retrieval |
| “What applies to TF-99318?” | safety bulletin dominates |
| valve part for ZX-440A | exact model/part controls |
| unsafe technician shortcut | authoritative contradiction shown; no unsafe recommendation |
| unknown serial/model | clarify/abstain |

Display intent, filters, candidates, authority, rerank, evidence, answer and citation.

## 14. Submission & Assessment

Submit architecture, parser/chunk decisions, overlap rationale, metadata, latency budget, retrieval matrix, ADK design, demo code/output, limitations and production plan. Weight critical decisions heavily: parsing/layout 10, chunking 15, exact/hybrid retrieval 15, authority/safety 15, latency/freshness 10, ADK 10, demo 15, discovery/FDE defense 10.

## 15. FDE Defense

Defend parser choices, warning-aware chunks, overlap, exact identifiers, source authority, index threshold, 2-second SLA, offline compromise, minimum agent architecture, approval boundaries and what changes at 100× scale.
