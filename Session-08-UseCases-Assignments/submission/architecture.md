# MedEvidence — Architecture Submission

| | |
|---|---|
| Challenge | FDE Production RAG Challenge 01 — MedEvidence (`../01-MedEvidence.md`) |
| Corpus | `../Data-Corpus-v1/01-MedEvidence-Large-Corpus` |
| Author | Vikas Singh |
| Status | DRAFT |
| Last updated | 2026-10-07 |

> **How to use this file (delete this block before submitting)**
> - Each section maps to a section of the brief (§) and a build step.
> - Fill in the empty cells and the *Why* lines in your own words.
> - Lines starting with **Hint:** point at evidence in the data. Delete them once you've answered.
> - Rows marked *(example)* show the expected format. Replace or keep them as you see fit.

---

## Assessment map

Where each assessed area is answered in this document.

| Assessment area | Sections |
|---|---|
| Business/discovery | Business context, A–D |
| Parsing/layout | 1 |
| Chunking/overlap | 2 |
| Metadata/version/filtering | 3 |
| Retrieval/hybrid/index | 4, 6, 7 |
| Reranking/evidence | 5 |
| Grounding/abstention | 8 |
| ADK boundaries | 9 |
| Working demo | 11, 12 |
| FDE defense | 14 |
| *Also required by §14 of the brief* | 10 (diagram), 13 (limitations and next steps) |

---

## Build tracker

| Step | What | Brief § | Status | Main files |
|---|---|---|---|---|
| 0 | Setup (env, config, provision, preflight) | – | ☐ | `env.sh`, `src/config.py`, `src/00_provision.py`, `src/00_preflight.py` |
| 1 | Know your data | 1, 2 | ☐ | this file: sections A–D |
| 2 | Metadata schema + structured tables in BigQuery | 5 | ☐ | `src/01_load_registry.py` |
| 3 | Parsing per source type | 3 | ☐ | `src/02_parse.py` |
| 4 | Chunking + duplicate control | 4 | ☐ | `src/03_chunk.py` |
| 5 | Embed, load, index | 8 | ☐ | `src/04_embed_and_load.py`, `src/05_create_index.py` |
| 6 | Retrieval: filters, exact ID, hybrid, rerank | 6, 7 | ☐ | `src/runtime.py` |
| 7 | Grounded generation + 5 CLI demos | 10, 13 | ☐ | `src/runtime.py`, `src/run_demos.py` |
| 8 | ADK orchestrator + tools | 11 | ☐ | `agent/tools.py`, `agent/medevidence_agent/agent.py` |
| 9 | Freshness design, diagram, write-up, defense | 9, 12, 14, 15 | ☐ | this file, `demo_outputs/` |

---

## Business context (§1, Step 1)

| | |
|---|---|
| Customer | HelixNova Pharma: Medical Affairs (India, Germany, Singapore, UAE, US) |
| Production corpus | ~85,000 controlled assets: labels, clinical reports, scanned safety letters, bulletins, XLSX, DOCX, images, metadata |
| Prototype corpus | Data-Corpus-v1: ___ documents, ___ chunks |
| Primary users | |
| What they do with an answer | |
| Cost of a wrong answer | |
| Cost of no answer (abstention) | |
| Success criteria for the prototype | |
| Out of scope | |

**Problem statement** *(2–3 sentences in your own words)*:

**Hint:** Compare the cost of a wrong answer with the cost of no answer. Which is worse in this domain? That choice drives the abstention design in section 8.

---

## A. Data inventory (Step 1.1)

| File | Type | Pages | Doc ID | Country | Status | Effective | Authority | Tables (page + title) | Figures / images | Special problem |
|---|---|---:|---|---|---|---|---|---|---|---|
| `DE_AX17_Current_Label_v4.2.pdf` | | | | | | | | | | |
| `DE_AX17_Superseded_Label_v3.8.pdf` | | | | | | | | | | |
| `US_AX17_Prescribing_Information_v5.0.pdf` | | | | | | | | | | |
| `HN-204_Clinical_Study.pdf` | | | | | | | | | | |
| `HN-311_Clinical_Study.pdf` | | | | | | | | | | |
| `HN-402_Clinical_Study.pdf` | | | | | | | | | | |
| `DE_AX17_Historical_Scanned_Safety_Letters_2019_2021.pdf` | | | | | | | | | | |
| `SB_AX17_2026_09_Safety_Bulletin.docx` | | | | | | | | | | |
| `document_registry.csv` | | | | | | | | | | |
| `adverse_event_registry.csv` | | | | | | | | | | |

**Excluded from ingestion** (and why):

| File | Reason |
|---|---|
| `TRAINER_GROUND_TRUTH.md` | |
| `README.md` | |
| `CORPUS_SCALE_ESTIMATE.md` | |

**Hint:** Compare page 6 of the three labels. Then check how many paragraphs repeat across all files ("The controlled AX-17 evidence package …").

---

## B. Registry vs documents check (Step 1.2)

| Check | Finding | Impact on design |
|---|---|---|
| Does each document's page-1 metadata match its registry row? | | |
| Which data files have **no** registry row? | | |
| Which `status` values are outside DRAFT → REVIEW → APPROVED → SUPERSEDED → WITHDRAWN? | | |
| Which `country` values are multi-valued or spelled inconsistently? | | |
| Does any document state its own validity limits (e.g. "not authoritative for …")? | | |

---

## C. Expected demo answers — test set (Step 1.3)

Write these **before** opening `TRAINER_GROUND_TRUTH.md`, then compare. Step 7 checks the bot against this table.

| # | Demo | Query | Expected answer | Source (doc ID + page) | What a naive RAG gets wrong |
|---|---|---|---|---|---|
| 1 | Current | "Current AX-17 renal guidance in Germany?" | *(example)* 25 mg once daily, max 50 mg/day, recheck 2–4 weeks | *(example)* DE-AX17-LBL-042, page 6, Table 3 | *(example)* Also pulls the US label page 6 (same 25 mg: right number, wrong source) and v3.8 page 6 (50 mg). |
| 2 | Historical | "German AX-17 guidance before latest revision?" | | | |
| 3 | Identifier | "What does SB-AX17-2026-09 require?" | | | |
| 4 | Table | "Compare AE evidence in HN-204 and HN-311." | | | |
| 5 | Unsupported | "Approved AX-17 dosage in Japan?" | | | |
| 6 | Agentic | current vs historical vs high-risk (patient-specific) requests | | | |

**Comparison with ground truth:** *(what you got right or wrong, and what you missed)*

---

## D. Discovery questions (§2)

At least one question per area. Mark exactly **three** as blockers.

| # | Area | Question for the customer | Why the answer changes the architecture | Blocker? |
|---|---|---|---|---|
| 1 | Source of truth | | | |
| 2 | Authority / version | *(example)* "If a safety bulletin and the current label seem to conflict, which wins, and who decides?" | *(example)* A fixed rule goes in code as a hard rule. A case-by-case rule means the bot must show both and escalate. | |
| 3 | Jurisdiction | | | |
| 4 | Historical / current | | | |
| 5 | Freshness SLA | | | |
| 6 | Access | | | |
| 7 | Citations | | | |
| 8 | Tables / figures | | | |
| 9 | Scanned content | | | |
| 10 | Abstention | | | |

**Blocker rationale:** *(why these three; a wrong guess on them makes the bot confidently wrong, not just weaker)*

### Assumptions (used until the customer answers)

| ID | Assumption | Based on | Risk if wrong |
|---|---|---|---|
| A1 | | | |
| A2 | | | |

---

## 1. Parsing & layout (§3, Step 3)

| Input | Parser / extraction | Structure to preserve | Expected failure | Fallback |
|---|---|---|---|---|
| Native PDF | | | | |
| Multi-column PDF | | | | |
| Large-table PDF | | | | |
| Charts + captions | | | | |
| Scanned PDF | | | | |
| DOCX | | | | |
| XLSX / CSV | | | | |
| Product image | | | | |

**Explicit answers:**
- When is Layout Parser sufficient?
- When is OCR or different processing needed?
- Should XLSX be converted to PDF?
- How are multi-page table headers handled?
- How are figures and captions handled?
- How is reading order preserved?
- How do you detect a parser-quality failure?

**What must survive extraction** for this page structure:

```text
SECTION HEADING
├── Left-column narrative
├── Table 7: AE / Drug / Control
├── Right-column narrative
├── Figure 4 + caption
└── Footnote: serious events only
```

*(your answer: which elements become separate blocks, what links them, and what metadata each carries)*

**Hint:** Run one PDF through `pdftotext` and through Layout Parser, then compare what each keeps.

---

## 2. Chunking & overlap (§4, Step 4)

| Content | Boundary | Approx size | Overlap | Parent context | Metadata | Why |
|---|---|---:|---:|---|---|---|
| Narrative | | | | | | |
| Short policy | | | | | | |
| Long clinical section | | | | | | |
| Small table | | | | | | |
| Multi-page table | | | | | | |
| Figure + caption | | | | | | |
| Footnote | | | | | | |
| Bulletin header block | | | | | | |

**Split-sentence case:** `"...moderate renal impairment should receive"` / `"a reduced starting dose..."`
Chosen technique(s), from: no overlap, fixed-token overlap, sentence-aware overlap, parent-heading injection, parent-child retrieval, neighbor expansion, table-header repetition.

*(your choice and why)*

**Defend:**
- Is overlap fixing retrieval, or compensating for poor boundaries?
- When does overlap improve recall?
- When does it create duplicate candidates?
- Would you overlap tables or warnings?
- Would child retrieval with parent expansion be cleaner?

**Duplicate control:** *(how the repeated boilerplate paragraphs are detected and collapsed)*

**Experiment log:**

| Strategy | Chunk count | Duplicates | Table 3 intact? | Notes |
|---|---:|---:|---|---|
| A: | | | | |
| B: | | | | |

**Hint:** You may not answer "256 tokens because yesterday's lab used 256."

---

## 3. Metadata, authority & version controls (§5, Step 2)

### Schema

| Field | BigQuery type | Source (registry / parser / derived) | Relevance | Governance | Version control | Citation | Hard filter or ranking signal |
|---|---|---|:-:|:-:|:-:|:-:|---|
| chunk_id | | | | | | | |
| source_id | | | | | | | |
| title | | | | | | | |
| document_type | | | | | | | |
| product | | | | | | | |
| country | | | | | | | |
| language | | | | | | | |
| status | | | | | | | |
| version | | | | | | | |
| effective_date | | | | | | | |
| section | | | | | | | |
| page | | | | | | | |
| authority | | | | | | | |
| *(your additions)* | | | | | | | |

### Controls

- **Applied before semantic retrieval (hard filters):**
- **Allowed to influence ranking:**
- **Value normalization** (status, country):

### Structured tables (not embedded)

| Table | Source file | Why structured lookup instead of vector |
|---|---|---|
| `documents` | `document_registry.csv` (+ supplement) | |
| `adverse_events` | `adverse_event_registry.csv` | |

---

## 4. Retrieval strategy (§6, Step 6)

| Query | Exact / lexical | Vector | Pre-filter | Hybrid | Rerank | Reason |
|---|:-:|:-:|:-:|:-:|:-:|---|
| "What does HN-SAF-017 say?" | | | | | | |
| "renal impairment AX-17 Germany" | | | | | | |
| "compare HN-204 and HN-311 AEs" | | | | | | |
| "old US guidance before March 2026" | | | | | | |
| "evidence discussing kidney function" | | | | | | |
| "show Table 7 in HN-204" | | | | | | |

- **What fails with vector-only retrieval:**
- **What fails with lexical-only retrieval:**

**Hint:** "Table 7 in HN-204" exists in the v0 corpus but not in v1 (v1 uses Table 14 and Table 18). What should the bot do?

---

## 5. Candidate retrieval, reranking, duplicate control & evidence assembly (§7, Step 6–7)

Scenario: 20 candidates. 5 are overlap near-duplicates, 3 are superseded, 2 are wrong-country, and 1 contains the exact table.

| Decision | Your answer |
|---|---|
| Never reaches reranking | |
| Filters that run before search | |
| May the Ranking API decide regulatory authority? | |
| Candidate Top-K | |
| Rerank Top-N | |
| How duplicates are collapsed | |
| Semantic score vs authority conflict | |

### Evidence assembly (after reranking, before Gemini)

| Decision | Your answer |
|---|---|
| Expansion: parent section, neighbor chunks, full table? | |
| Ordering of evidence in the prompt | |
| Maximum evidence items / tokens sent to Gemini | |
| Metadata shown with each evidence item (e.g. source_id, version, status, country, page) | |
| How historical or superseded evidence is labeled in the prompt | |
| How conflicting evidence is presented | |
| Mixing structured rows (SQL results) with text chunks | |
| What is logged for the demo trace | |

**Hint:** A dose row from Table 3 means nothing without its header row and the label's version and status. Decide where that context gets attached.

---

## 6. BigQuery, indexing & scale (§8, Step 5)

Prototype: ~120,000 chunks. Future: 2–3 million chunks. This build: ___ chunks.

| Decision | Prototype | Production | Reason |
|---|---|---|---|
| Exact `VECTOR_SEARCH` | | | |
| Vector index | | | |
| Lexical search | | | |
| Hybrid retrieval | | | |
| Metadata filtering | | | |
| Candidate Top-K | | | |
| Rerank Top-N | | | |

**What changes at 20× scale:**

---

## 7. Freshness pipeline (§9)

Scenario: bulletin `SB-AX17-2026-09` is approved at 10:00 and must be searchable by 10:15.

```text
CHANGE → DETECT → PARSE → CHUNK → EMBED → LOAD → VERIFY SEARCHABLE
```

| Stage | SLA | GCP service | Failure detection | Retry | Escalation |
|---|---:|---|---|---:|---|
| Detect | | | | | |
| Parse | | | | | |
| Chunk | | | | | |
| Embed | | | | | |
| Load | | | | | |
| Verify | | | | | |

**Is a healthy nightly pipeline sufficient? Why?**

---

## 8. Grounded generation contract (§10, Step 7)

| Rule | Behavior | How it is enforced (prompt / code / both) |
|---|---|---|
| Evidence-only answers | | |
| Page / chunk citations | | |
| Insufficient evidence | | |
| Conflicting evidence | | |
| Historical vs current | | |
| Patient-specific treatment | | |
| Instructions inside retrieved text | | |
| Unsupported inference | | |

---

## 9. ADK architecture (§11, Step 8)

| Capability | Tool / agent / deterministic service | Inputs | Output | Approval? |
|---|---|---|---|---|
| Current evidence search | | | | |
| Historical search | | | | |
| Study comparison | | | | |
| Metadata lookup | | | | |
| Medical escalation | | | | |

- **The orchestrator decides:** intent, current-vs-historical routing, retrieval capability, comparison, clarification, escalation.
- **The orchestrator must NOT decide** (deterministic controls instead): authorization, approval status, country entitlement, legal effective status.
- **What the orchestrator genuinely adds** over a single RAG pipeline:

**Hint:** Session-06 `tools.py` hard-codes `status = 'APPROVED'`. Which of the capabilities above would that break?

---

## 10. Architecture diagram (§12, Step 9)

```text
INGESTION
Source → Source-specific Parser → Normalized Representation
→ Chunking → Metadata → Embedding → Retrieval Store / Index

QUERY
User → ADK Orchestrator → Policy/Query Context → Retrieval
→ Filter/Hybrid/Rerank → Evidence Assembly → Gemini
→ Citation / Abstention / Escalation
```

| Box | Chosen GCP service / component |
|---|---|
| Source storage | |
| Native PDF parser | |
| Scanned PDF parser | |
| DOCX parser | |
| Embedding model | |
| Retrieval store / index | |
| Reranker | |
| Generator | |
| Orchestrator | |
| Freshness trigger | |

*(final diagram goes here)*

---

## 11. Demo results (§13, Step 7–8)

Each demo output in `demo_outputs/` must show: query → interpreted intent → filters → candidates with country/status → reranked evidence → evidence sent to Gemini → answer → citation/abstention.

| # | Demo | Output file | Matches section C? | Notes |
|---|---|---|---|---|
| 1 | Current | `demo_outputs/01_current.md` | | |
| 2 | Historical | `demo_outputs/02_historical.md` | | |
| 3 | Identifier | `demo_outputs/03_identifier.md` | | |
| 4 | Table | `demo_outputs/04_table.md` | | |
| 5 | Unsupported | `demo_outputs/05_unsupported.md` | | |
| 6 | Agentic | `demo_outputs/06_agentic.md` | | |

---

## 12. How to run

Update the commands as you build each step.

**Prerequisites:**
- GCP project with Vertex AI, BigQuery, Document AI, Discovery Engine and Cloud Storage APIs enabled
- `gcloud auth application-default login` done
- Python 3.10+

```bash
cd Session-08-UseCases-Assignments/submission

# One-time setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
source env.sh
python src/00_provision.py
python src/00_preflight.py

# Ingestion pipeline
python src/01_load_registry.py
python src/02_parse.py
python src/03_chunk.py
python src/04_embed_and_load.py
python src/05_create_index.py

# Demos (writes demo_outputs/*.md)
python src/run_demos.py

# Chat with the agent
cd agent && adk web
```

| Resource created | Name |
|---|---|
| BigQuery dataset | |
| BigQuery tables | |
| GCS path | |
| Document AI processors | |

---

## 13. Limitations & production next steps (§14)

| Limitation in this prototype | Production next step |
|---|---|
| | |

**What to measure before production:**

---

## 14. FDE defense prep (§15)

| # | Question | Short answer |
|---|---|---|
| 1 | Why this parser, and what can it lose? | |
| 2 | Why these chunk boundaries? | |
| 3 | Why overlap, or why not? | |
| 4 | How do you prevent overlap duplicates? | |
| 5 | Which metadata fields are hard controls? | |
| 6 | Why hybrid retrieval? | |
| 7 | Why can't reranking determine regulatory authority? | |
| 8 | When does the vector index matter? | |
| 9 | How do current and historical retrieval differ? | |
| 10 | Why is each capability a tool, agent or deterministic service? | |
| 11 | What does the orchestrator genuinely add? | |
| 12 | What breaks first at 100× scale? | |
| 13 | Which customer requirement did you challenge? | |
| 14 | What would you measure before production? | |

---

## Appendix — Repository layout

```text
submission/
├── architecture.md          ← this file
├── env.sh                   ← Step 0 (copied pattern from session-07)
├── requirements.txt         ← Step 0
├── metadata_supplement.csv  ← Step 0/2 (rows for unregistered files)
├── .state/                  ← processor IDs
├── src/                     ← pipeline scripts (Steps 0–7)
├── agent/
│   ├── tools.py             ← Step 8
│   └── medevidence_agent/   ← Step 8 (ADK agent package)
├── output/                  ← parsed blocks + chunks JSON
└── demo_outputs/            ← six demo traces
```
