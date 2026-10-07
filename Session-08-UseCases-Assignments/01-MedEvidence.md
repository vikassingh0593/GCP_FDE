# FDE Production RAG Challenge 01 — MedEvidence

> **Participant mode:** Architecture decision + production RAG build  
> **Architecture/design time:** ~60 minutes  
> **Demo build time:** Maximum 2 hours  
> **Starting point:** Reuse the Google-native RAG code from the previous hands-on wherever appropriate.  
> **Assessment:** Decision quality, production thinking, retrieval design, and a working demonstrator.


## 1. Customer Brief & Data Landscape

HelixNova Pharma operates in India, Germany, Singapore, UAE and the US. Medical Affairs teams search ~85,000 controlled assets: prescribing PDFs, 80–400 page clinical reports, scanned safety letters, urgent bulletins, XLSX adverse-event workbooks, DOCX response letters, product images and repository metadata.

Typical questions:

> “What is the currently approved guidance for Product AX-17 for moderate renal impairment in Germany?”

> “Compare adverse-event rates in Study HN-204 and HN-311 and show the evidence.”

Documents move through `DRAFT → REVIEW → APPROVED → SUPERSEDED → WITHDRAWN` and carry jurisdiction. A superseded document is invalid for current guidance but may be correct for a historical question. Global scientific evidence must not silently substitute for local regulatory guidance.

| Input | Layout / Concern | Update Pattern |
|---|---|---|
| Prescribing PDF | headings, tables, footnotes | monthly/event |
| Clinical PDF | multi-column, tables, charts, references | low |
| Scanned safety letter | image-only, stamps | rare |
| Safety bulletin | warning boxes, effective date | immediate |
| XLSX | sheets, merged headers, formulas | weekly |
| DOCX | hierarchy, tables, approval state | weekly |
| Product image | image + labels | low |
| Repository metadata | country, status, dates, owner | continuous |

**Constraint:** one parser, one chunking policy and one retriever are not automatically acceptable.

---

## 2. Discovery Gate

Write the **10 highest-value discovery questions**. At least one must materially affect each of: source of truth, authority, jurisdiction, historical/current behavior, freshness SLA, access, citations, tables/figures, scanned content and abstention.

| Decision Area | Critical Question | Why It Changes Architecture |
|---|---|---|
| Source of truth | | |
| Authority/version | | |
| Jurisdiction | | |
| Freshness | | |
| Access | | |
| Citation | | |
| Complex content | | |
| Abstention | | |

Mark the **three blockers** without which you would not finalize production architecture.

---

## 3. Parsing & Layout Decision

You used Document AI Layout Parser yesterday. Decide where it is actually appropriate.

| Input | Parser / Extraction | Structure to Preserve | Expected Failure | Fallback |
|---|---|---|---|---|
| Native PDF | | | | |
| Multi-column PDF | | | | |
| Large-table PDF | | | | |
| Charts + captions | | | | |
| Scanned PDF | | | | |
| DOCX | | | | |
| XLSX | | | | |
| Product image | | | | |

Explicitly answer: When is Layout Parser sufficient? When is OCR/different processing needed? Should XLSX be converted to PDF? How are multi-page table headers, figures/captions, reading order and parser-quality failures handled?

For this page, state what must survive extraction:

```text
SECTION HEADING
├── Left-column narrative
├── Table 7: AE / Drug / Control
├── Right-column narrative
├── Figure 4 + caption
└── Footnote: serious events only
```

---

## 4. Chunking & Overlap Design

You may not answer “256 tokens because yesterday's lab used 256.”

| Content | Boundary | Approx Size | Overlap | Parent Context | Metadata | Why |
|---|---|---:|---:|---:|---|---|
| Narrative | | | | | | |
| Short policy | | | | | | |
| Long clinical section | | | | | | |
| Small table | | | | | | |
| Multi-page table | | | | | | |
| Figure + caption | | | | | | |
| Footnote | | | | | | |

Consider a boundary splitting: `"...moderate renal impairment should receive"` / `"a reduced starting dose..."`.

Decide among no overlap, fixed-token overlap, sentence-aware overlap, parent-heading injection, parent-child retrieval, neighbor expansion and table-header repetition.

Defend: Is overlap fixing retrieval or compensating for poor boundaries? When does it improve recall? When does it create duplicate candidates? Would you overlap tables/warnings? Would child retrieval + parent expansion be cleaner?

---

## 5. Metadata, Authority & Version Controls

Design the metadata schema beginning with:

`chunk_id, source_id, title, document_type, product, country, language, status, version, effective_date, section, page, authority`

| Field | Relevance | Governance | Version Control | Citation | Hard Filter / Ranking Signal |
|---|---:|---:|---:|---:|---|
| country | | | | | |
| status | | | | | |
| effective_date | | | | | |
| product | | | | | |
| document_type | | | | | |
| authority | | | | | |
| ... | | | | | |

Which controls must apply **before semantic retrieval**? Which may influence ranking?

---

## 6. Retrieval Strategy

| Query | Exact/Lexical | Vector | Pre-filter | Hybrid | Rerank | Reason |
|---|---:|---:|---:|---:|---:|---|
| “What does HN-SAF-017 say?” | | | | | | |
| “renal impairment AX-17 Germany” | | | | | | |
| “compare HN-204 and HN-311 AEs” | | | | | | |
| “old US guidance before March 2026” | | | | | | |
| “evidence discussing kidney function” | | | | | | |
| “show Table 7 in HN-204” | | | | | | |

Explain what fails with vector-only retrieval and what fails with lexical-only retrieval.

---

## 7. Candidate Retrieval, Reranking & Duplicate Control

Twenty candidates arrive: five are overlap-created near-duplicates, three are superseded, two are wrong-country, one contains the exact table.

Decide:
- what should never reach reranking;
- which filters precede search;
- whether Ranking API may determine regulatory authority;
- candidate Top-K and rerank Top-N;
- how duplicates are collapsed;
- what happens when semantic score conflicts with authority.

---

## 8. BigQuery, Indexing & Scale

Prototype: **~120,000 chunks**. Future: **2–3 million chunks**.

| Decision | Prototype | Production | Reason |
|---|---|---|---|
| Exact `VECTOR_SEARCH` | | | |
| Vector index | | | |
| Lexical search | | | |
| Hybrid retrieval | | | |
| Metadata filtering | | | |
| Candidate Top-K | | | |
| Rerank Top-N | | | |

Explain what changes at 20× corpus scale.

---

## 9. Freshness Pipeline

Safety bulletin `SB-AX17-2026-09` is approved at 10:00 and must be searchable by 10:15.

```text
CHANGE → DETECT → PARSE → CHUNK → EMBED → LOAD → VERIFY SEARCHABLE
```

| Stage | SLA | Failure Detection | Retry | Escalation |
|---|---:|---|---:|---:|
| Detect | | | | |
| Parse | | | | |
| Chunk | | | | |
| Embed | | | | |
| Load | | | | |
| Verify | | | | |

Is a healthy nightly pipeline sufficient? Why?

---

## 10. Grounded Generation Contract

Define rules for evidence-only answers, page/chunk citations, insufficient evidence, conflicting evidence, historical/current distinctions, patient-specific treatment boundaries, malicious instructions inside retrieved text and unsupported inference.

---

## 11. ADK Architecture

Only now introduce the agentic layer.

| Capability | Tool / Agent / Deterministic Service | Inputs | Output | Approval? |
|---|---|---|---|---|
| Current evidence search | | | | |
| Historical search | | | | |
| Study comparison | | | | |
| Metadata lookup | | | | |
| Medical escalation | | | | |

Define exactly what the **orchestrator** decides: intent, current-vs-historical routing, retrieval capability, comparison, clarification, escalation.

Also define what it must **not** decide: authorization, approval status, country entitlement or legal effective status where deterministic controls should govern.

---

## 12. Architecture Submission

Show both paths and name chosen Google Cloud services.

```text
INGESTION
Source → Source-specific Parser → Normalized Representation
→ Chunking → Metadata → Embedding → Retrieval Store / Index

QUERY
User → ADK Orchestrator → Policy/Query Context → Retrieval
→ Filter/Hybrid/Rerank → Evidence Assembly → Gemini
→ Citation / Abstention / Escalation
```

---

## 13. Two-Hour Build Challenge

Reuse yesterday's RAG project. Build a **MedEvidence prototype** with a small corpus:

| Document | Requirement |
|---|---|
| Germany current AX-17 label | approved/current |
| Germany old AX-17 label | superseded |
| US AX-17 label | approved, wrong country for German query |
| Study HN-204 | table evidence |
| Study HN-311 | comparable evidence |
| Safety bulletin | newest/high-authority |

At least one source must contain a table and one must contain a layout challenge.

### Mandatory demos

| Demo | Query | Expected Behavior |
|---|---|---|
| Current | “Current AX-17 renal guidance in Germany?” | current German evidence; citation |
| Historical | “German AX-17 guidance before latest revision?” | historical evidence eligible |
| Identifier | “What does SB-AX17-2026-09 require?” | exact/hybrid retrieval |
| Table | “Compare AE evidence in HN-204 and HN-311.” | evidence from both studies |
| Unsupported | “Approved AX-17 dosage in Japan?” | abstain/clarify |
| Agentic | current vs historical vs high-risk requests | correct ADK routing |

For every query display: query → interpreted intent → filters → candidates with country/status → reranked evidence → evidence sent to Gemini → answer → citation/abstention.

---

## 14. Submission & Assessment

Submit: `architecture.md`, diagram, completed matrices, discovery questions/assumptions, chunking+overlap rationale, metadata schema, retrieval strategy, ADK design, working code, six demo outputs, limitations and production next steps.

| Assessment Area | Weight |
|---|---:|
| Business/discovery | 10 |
| Parsing/layout | 12 |
| Chunking/overlap | 15 |
| Metadata/version/filtering | 12 |
| Retrieval/hybrid/index | 15 |
| Reranking/evidence | 8 |
| Grounding/abstention | 8 |
| ADK boundaries | 8 |
| Working demo | 8 |
| FDE defense | 4 |

---

## 15. FDE Defense

Be prepared to answer:

1. Why this parser, and what can it lose?
2. Why these chunk boundaries?
3. Why overlap—or why not?
4. How do you prevent overlap duplicates?
5. Which metadata fields are hard controls?
6. Why hybrid retrieval?
7. Why can't reranking determine regulatory authority?
8. When does the vector index matter?
9. How do current and historical retrieval differ?
10. Why is each capability a tool, agent or deterministic service?
11. What does the orchestrator genuinely add?
12. What breaks first at 100× scale?
13. Which customer requirement did you challenge?
14. What would you measure before production?

> **FDE principle:** Turn messy requirements + heterogeneous data + risk/scale/freshness into defensible engineering decisions and a working customer demonstration.
