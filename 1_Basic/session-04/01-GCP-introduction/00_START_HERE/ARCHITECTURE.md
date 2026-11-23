# Architecture

```text
Markdown policy corpus
      ↓
Cloud Storage
      ↓
Python structure-aware chunker
      ↓
JSONL chunks + provenance
      ↓
BigQuery knowledge_chunks
      ↓
AI.EMBED
      ↓
knowledge_embeddings
      ↓
┌─────────────┬──────────────┐
│ Lexical     │ Semantic     │
└──────┬──────┴──────┬───────┘
       └── Hybrid ───┘
             ↓
        Candidate set
             ↓
     Google Ranking API
             ↓
       Best evidence
             ↓
           Gemini
             ↓
 Citation / authority / refusal
```

## FDE contract

1. Retrieval must preserve provenance.
2. Approved/current evidence outranks superseded evidence as authority.
3. Exact identifiers must be retrievable lexically.
4. Paraphrases must be retrievable semantically.
5. Hybrid should preserve both signals.
6. Generation may use only supplied evidence.
7. Unsupported questions must be qualified/refused.
8. Retrieval quality is evaluated separately from generation quality.
