# Google-Native Production RAG — Visual Walkthrough

## What Are We Building?

In this hands-on, we are building a **production-oriented Retrieval-Augmented Generation (RAG) pipeline using Google Cloud services**.

The objective is not simply:

```text
PDF → Gemini → Answer
```

Instead, we deliberately separate the system into engineering stages:

```text
                    OFFLINE / INGESTION PATH

 ┌──────────────┐
 │ Complex PDF  │
 │ text         │
 │ tables       │
 │ figures      │
 │ hierarchy    │
 └──────┬───────┘
        │
        ▼
 ┌──────────────────────────────┐
 │ Google Cloud Storage         │
 │ Source document storage      │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Document AI Layout Parser    │
 │ Parse structure + layout     │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Context-Aware Chunks         │
 │ headings + text + structure  │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Gemini Embedding Model       │
 │ text → numerical vector      │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ BigQuery                     │
 │ chunk + metadata + vector    │
 └──────────────────────────────┘


                     ONLINE / QUERY PATH

 ┌──────────────────┐
 │ User Question    │
 └────────┬─────────┘
          │
          ▼
 ┌──────────────────────────────┐
 │ Gemini Embedding Model       │
 │ question → query vector      │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ BigQuery VECTOR_SEARCH       │
 │ Retrieve candidates          │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Google Ranking API           │
 │ Rerank candidate evidence    │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Best Evidence                │
 │ Top supporting chunks        │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Gemini                       │
 │ Grounded generation          │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Answer + Chunk Citations     │
 └──────────────────────────────┘
```

---

# 1. Why RAG?

A foundation model knows what it learned during training, but it does not automatically know our private enterprise documents.

For example:

```text
USER
"What does policy AI-RAG-017 say?"
          │
          ▼
       GEMINI
          │
          ▼
Does Gemini inherently know our
synthetic enterprise policy?

          NO
```

We therefore retrieve relevant enterprise knowledge first:

```text
QUESTION
   │
   ▼
RETRIEVE RELEVANT EVIDENCE
   │
   ▼
ADD EVIDENCE TO MODEL CONTEXT
   │
   ▼
GENERATE ANSWER FROM EVIDENCE
```

This is:

# Retrieval-Augmented Generation

```text
R = Retrieve
A = Augment
G = Generate
```

---

# 2. The Two Pipelines in RAG

A production RAG system really contains **two different pipelines**.

## Pipeline A — Knowledge Ingestion

Runs when documents are added or changed.

```text
DOCUMENT
   ↓
STORE
   ↓
PARSE
   ↓
CHUNK
   ↓
EMBED
   ↓
INDEX / STORE
```

## Pipeline B — Question Answering

Runs when a user asks something.

```text
QUESTION
   ↓
EMBED QUESTION
   ↓
RETRIEVE
   ↓
RERANK
   ↓
ASSEMBLE EVIDENCE
   ↓
GENERATE
   ↓
ANSWER
```

This distinction is fundamental.

We do **not** parse the PDF again every time someone asks a question.

---

# 3. Service 1 — Google Cloud Storage

## What is it?

Google Cloud Storage is object storage.

Think of it as the place where enterprise source files can live:

```text
Cloud Storage Bucket

├── policies/
│   ├── refund-policy.pdf
│   └── security-policy.pdf
│
├── reports/
│   └── annual-report.pdf
│
└── manuals/
    └── operations-manual.pdf
```

In our lab, the source is:

```text
Aurelia_Retail_AI_Operations_Report.pdf
```

## Why use Cloud Storage?

Because downstream Google Cloud services can work with documents stored in GCP.

```text
LOCAL FILE
    ↓
CLOUD STORAGE
    ↓
DOCUMENT PROCESSING
```

Cloud Storage is **not the RAG retrieval engine**.

Its job here is source-document storage.

---

# 4. Service 2 — Document AI Layout Parser

A PDF is not simply a string of text.

It may contain:

```text
PAGE

┌────────────────────────────────────┐
│ 2. Customer Experience             │
│                                    │
│ Paragraph text...                  │
│                                    │
│ ┌────────┬────────┬─────────────┐  │
│ │ Region │ Growth │ Margin      │  │
│ ├────────┼────────┼─────────────┤  │
│ │ India  │ ...    │ ...         │  │
│ └────────┴────────┴─────────────┘  │
│                                    │
│       📈 Churn Trend               │
│                                    │
│ Q1 → Q2 → Q3 → Q4                 │
└────────────────────────────────────┘
```

Naively extracting text can destroy important structure.

For example:

```text
Singapore 22.9 18.4 India 14.2 UAE...
```

may lose the meaning of rows, columns and headings.

Document AI Layout Parser attempts to understand document structure.

```text
PDF
 ↓
DOCUMENT AI LAYOUT PARSER
 ↓
Document Structure
 ├── headings
 ├── paragraphs
 ├── tables
 ├── figures
 └── hierarchy
```

This is why we chose it instead of immediately doing:

```python
text.split(...)
```

---

# 5. Parsing Is Not Chunking

These are related but different ideas.

## Parsing

```text
"What structures exist in this document?"
```

## Chunking

```text
"How should those structures be divided into retrievable units?"
```

The parser first understands the document.

Then we obtain context-aware chunks.

---

# 6. Context-Aware Chunking

Suppose the document contains:

```text
3. AI Service Operations

Grounding Audit

The Q4 grounding audit pass rate was 97%.
```

A poor chunk might become:

```text
The Q4 grounding audit pass rate was 97%.
```

It contains the fact but loses some context.

A context-aware representation can preserve structural information:

```text
3. AI Service Operations
Grounding Audit

The Q4 grounding audit pass rate was 97%.
```

That gives retrieval more semantic clues.

In our lab we configured:

```text
CHUNK_SIZE = 256
INCLUDE_ANCESTOR_HEADINGS = true
```

Our small training PDF currently produces:

```text
5 context-aware chunks
```

This is enough to understand the pipeline, although a production corpus may contain thousands or millions of chunks.

---

# 7. Inspect Before Embedding

This is an important engineering habit.

Do not immediately convert everything into vectors.

First inspect:

```text
SOURCE PDF
   ↓
PARSER
   ↓
CHUNKS
   ↓
        STOP
   ↓
INSPECT THEM
```

Questions to ask:

```text
Are headings preserved?

Are tables understandable?

Are chunks too large?

Are chunks too small?

Did unrelated sections merge?

Did important context disappear?
```

Because:

> Bad chunks produce bad retrieval regardless of how powerful the embedding model is.

---

# 8. Service 3 — Gemini Embeddings

LLMs work with language.

Vector search works with numerical representations.

An embedding model transforms text into a vector.

Conceptually:

```text
"Singapore FY2026 growth"
          ↓
    EMBEDDING MODEL
          ↓
[0.018, -0.042, 0.071, ...]
```

The actual vector contains hundreds of numerical dimensions.

In our lab:

```text
gemini-embedding-001
```

with:

```text
768 dimensions
```

So every chunk becomes:

```text
chunk-0000
   │
   ├── text
   │
   └── embedding
       [x1, x2, x3, ... x768]
```

---

# 9. Document Embeddings vs Query Embeddings

This is an important detail.

When storing knowledge:

```text
DOCUMENT CHUNK
     ↓
RETRIEVAL_DOCUMENT
     ↓
VECTOR
```

When a user asks a question:

```text
USER QUESTION
     ↓
RETRIEVAL_QUERY
     ↓
VECTOR
```

The embedding model is being told what role the text plays in retrieval.

---

# 10. Service 4 — BigQuery

We then store our knowledge representation in BigQuery.

Conceptually:

| chunk_id | content | embedding |
|---|---|---|
| chunk-0000 | Regional performance... | `[0.01, ...]` |
| chunk-0001 | Customer experience... | `[0.04, ...]` |
| chunk-0002 | AI service operations... | `[-0.02, ...]` |
| ... | ... | ... |

So BigQuery is storing both:

```text
HUMAN-READABLE KNOWLEDGE

content
```

and:

```text
MACHINE-SEARCHABLE REPRESENTATION

embedding
```

---

# 11. What Happens When a Question Arrives?

Example:

```text
"What was Singapore's FY2026 growth?"
```

First:

```text
QUESTION
   ↓
Gemini Embedding
   ↓
QUERY VECTOR
```

Now the question and document chunks exist in the same semantic vector space.

Conceptually:

```text
Question Vector
      ●

          ● chunk A

                 ● chunk B

      ● chunk C

                           ● chunk D
```

We want chunks semantically closest to the question.

---

# 12. BigQuery VECTOR_SEARCH

BigQuery's `VECTOR_SEARCH` finds candidate vectors close to the query vector.

```text
QUERY VECTOR
      │
      ▼
┌─────────────────────┐
│ BigQuery            │
│ VECTOR_SEARCH       │
└──────────┬──────────┘
           │
           ▼
 Candidate chunks
```

For example, our run produced candidates similar to:

```text
chunk-0004
chunk-0000
chunk-0002
chunk-0001
```

This is **candidate generation**.

It does not mean the first candidate is necessarily the best final evidence.

---

# 13. What About the Vector Index?

We attempted to create an IVF vector index.

BigQuery rejected it because our table contains only 5 rows while IVF index creation requires a much larger table.

That is fine.

## Small Lab Corpus

```text
5 vectors
   ↓
VECTOR_SEARCH
   ↓
Direct similarity search
```

## Large Production Corpus

```text
Thousands / Millions of vectors
             ↓
        VECTOR INDEX
             ↓
     accelerated search
             ↓
        VECTOR_SEARCH
```

The key distinction is:

```text
VECTOR_SEARCH
= retrieval operation

VECTOR INDEX
= retrieval acceleration
```

An index is **not what makes RAG semantic**.

Embeddings provide the semantic representation.

---

# 14. Service 5 — Google Ranking API

Vector retrieval is excellent for finding candidates, but similarity alone does not always produce the best final ordering.

Our actual test demonstrated this.

Question:

```text
"What was Singapore's FY2026 growth?"
```

Vector retrieval produced:

```text
#1 chunk-0004
#2 chunk-0000
#3 chunk-0002
#4 chunk-0001
```

But `chunk-0000` contained the strongest evidence.

So we pass the candidates to Google's Ranking API:

```text
VECTOR SEARCH
     ↓
Broad Candidates
     ↓
┌──────────────────┐
│ Google Ranking   │
│ API              │
└────────┬─────────┘
         ↓
Better relevance order
```

Our result:

```text
chunk-0000    rank score ≈ 0.9758
chunk-0004    rank score ≈ 0.2358
```

This is a perfect illustration of the difference between:

```text
RETRIEVAL
"Find potentially relevant evidence."

             versus

RERANKING
"Given these candidates and this exact question,
which evidence is most relevant?"
```

---

# 15. Candidate Retrieval vs Reranking

Think of search as two stages:

```text
                   ALL KNOWLEDGE
                        │
                        ▼
              ┌──────────────────┐
              │ RETRIEVER        │
              │ High recall      │
              └────────┬─────────┘
                       │
                candidate set
                       │
                       ▼
              ┌──────────────────┐
              │ RERANKER         │
              │ Better precision │
              └────────┬─────────┘
                       │
                 best evidence
```

Retriever priority:

> Don't miss useful evidence.

Reranker priority:

> Put the best evidence at the top.

---

# 16. Service 6 — Gemini for Grounded Generation

Now we finally invoke the generative model.

Notice how late Gemini generation appears in the architecture.

```text
QUESTION
   +
TOP EVIDENCE
   ↓
GEMINI
   ↓
ANSWER
```

We instruct Gemini approximately:

```text
Answer using only the supplied evidence.

Cite supporting chunk IDs.

If the evidence is insufficient,
say that the answer cannot be determined.

Do not invent unsupported facts.
```

This changes the task from:

```text
"What do you know about this?"
```

to:

```text
"Given THIS evidence, answer THIS question."
```

That is grounding.

---

# 17. Why Citations Matter

Suppose Gemini answers:

```text
Singapore's FY2026 YoY growth was 22.9%.
[chunk-0000]
```

The citation provides an evidence trail:

```text
ANSWER
  │
  ▼
chunk-0000
  │
  ▼
Parsed source
  │
  ▼
Original PDF
```

For enterprise AI this matters because users, evaluators and engineers need to inspect:

```text
Where did this answer come from?
```

---

# 18. Abstention Is a Feature

Consider:

```text
"What is Aurelia Retail's FY2028 revenue guidance?"
```

Our source deliberately contains no FY2028 guidance.

A poor system does:

```text
NO EVIDENCE
    ↓
LLM guesses
    ↓
plausible-looking number
    ↓
❌ HALLUCINATION
```

A production-oriented system should do:

```text
NO SUFFICIENT EVIDENCE
          ↓
       ABSTAIN
          ↓
"Available evidence does not contain
 FY2028 revenue guidance."
```

A RAG system should therefore support two valid outcomes:

```text
             QUESTION
                │
                ▼
             RETRIEVE
                │
        ┌───────┴────────┐
        ▼                ▼
Evidence exists     Evidence missing
        │                │
        ▼                ▼
Answer + cite          Abstain
```

---

# 19. Complete Service Map

```text
┌─────────────────────────────────────────────────────────────┐
│                     INGESTION                               │
└─────────────────────────────────────────────────────────────┘

PDF
 │
 ▼
Cloud Storage
 │
 │ stores source object
 ▼
Document AI Layout Parser
 │
 │ understands layout / hierarchy
 ▼
Context-Aware Chunks
 │
 ▼
Gemini Embeddings
 │
 │ text → vector
 ▼
BigQuery
 │
 │ stores chunks + vectors
 ▼
Knowledge Base Ready


┌─────────────────────────────────────────────────────────────┐
│                       QUERY                                 │
└─────────────────────────────────────────────────────────────┘

User Question
 │
 ▼
Gemini Embeddings
 │
 │ question → vector
 ▼
BigQuery VECTOR_SEARCH
 │
 │ candidate retrieval
 ▼
Google Ranking API
 │
 │ relevance refinement
 ▼
Top Evidence
 │
 ▼
Gemini
 │
 │ grounded generation
 ▼
Answer + Citations
```

---

# 20. What Each GCP Service Is Responsible For

| Service | Responsibility |
|---|---|
| **Cloud Storage** | Store source documents |
| **Document AI Layout Parser** | Understand document layout and structure |
| **Document AI chunking** | Produce context-aware retrievable units |
| **Gemini Embeddings** | Convert chunks/questions into semantic vectors |
| **BigQuery** | Store chunks, metadata and vectors |
| **BigQuery VECTOR_SEARCH** | Retrieve semantically similar candidates |
| **BigQuery Vector Index** | Optional acceleration at larger scale |
| **Google Ranking API** | Rerank candidates by query relevance |
| **Gemini** | Generate grounded answers from evidence |

---

# 21. What We Are NOT Using Yet

## ADK

There is deliberately **no ADK in Project 1**.

```text
PROJECT 1
Build the RAG capability
        ↓
NO AGENT REQUIRED
```

RAG is a retrieval capability.

ADK is an agent-development/orchestration framework.

We will introduce ADK only after the RAG capability itself is understood and evaluated.

---

# 22. The Three-Project Journey

```text
PROJECT 1
BUILD
Google-Native Production RAG
        │
        ▼
"Can we retrieve and answer
 from enterprise knowledge?"
        │
        ▼
PROJECT 2
MEASURE
RAG Evaluation
        │
        ▼
"How do we know the system
 is actually good?"
        │
        ▼
PROJECT 3
OPERATE
ADK + Observability
        │
        ▼
"How do we expose this capability
 through an agent and understand
 what happens in production?"
```

Or simply:

# BUILD → MEASURE → OPERATE

---

# 23. Project 1 — Files and Their Role

```text
setup.sh
   │
   └── prepare GCP services/resources
          ↓
01_parse_document.py
   │
   └── PDF → Document AI → chunks
          ↓
02_inspect_chunks.py
   │
   └── inspect chunk quality
          ↓
03_embed_and_load.py
   │
   └── chunks → embeddings → BigQuery
          ↓
04_create_hybrid_index.py
   │
   └── vector index
       SKIPPED for tiny lab corpus
          ↓
05_retrieve_and_rerank.py
   │
   └── question
       → query embedding
       → VECTOR_SEARCH
       → Ranking API
          ↓
06_generate_answer.py
   │
   └── evidence → Gemini → grounded answer
          ↓
07_harness.py
   │
   └── interactive testing
```

---

# 24. The Most Important Mental Model

Do not think:

```text
RAG = Vector Database + LLM
```

Think:

```text
                 PRODUCTION RAG

SOURCE QUALITY
      ↓
PARSING QUALITY
      ↓
CHUNK QUALITY
      ↓
EMBEDDING QUALITY
      ↓
RETRIEVAL QUALITY
      ↓
RERANKING QUALITY
      ↓
CONTEXT QUALITY
      ↓
GENERATION QUALITY
      ↓
GROUNDING / CITATION / ABSTENTION
      ↓
FINAL USER EXPERIENCE
```

A failure at any layer can affect the final answer.

---

# 25. How an FDE Should Debug RAG

When an answer is wrong, don't immediately blame Gemini.

Ask:

```text
Wrong Answer
    │
    ▼
Was the correct source document available?
    │
    ▼
Was it parsed correctly?
    │
    ▼
Was the relevant information inside a useful chunk?
    │
    ▼
Was that chunk embedded correctly?
    │
    ▼
Did retrieval find it?
    │
    ▼
Did reranking keep/promote it?
    │
    ▼
Was it included in model context?
    │
    ▼
Did Gemini use it correctly?
```

This lets us distinguish:

```text
INGESTION FAILURE
vs
RETRIEVAL FAILURE
vs
RANKING FAILURE
vs
GENERATION FAILURE
```

That distinction becomes central in **Project 2 — RAG Evaluation**.

---

# Final Takeaway

The system we are building is not:

```text
PDF → LLM
```

It is:

```text
PDF
 ↓
STORE
 ↓
UNDERSTAND
 ↓
CHUNK
 ↓
EMBED
 ↓
STORE VECTORS
 ↓
RETRIEVE
 ↓
RERANK
 ↓
GROUND
 ↓
GENERATE
 ↓
CITE / ABSTAIN
```

And each responsibility is handled by an appropriate Google Cloud capability.

> **Production RAG is an information-retrieval system with an LLM at the end — not simply an LLM with a PDF attached.**
