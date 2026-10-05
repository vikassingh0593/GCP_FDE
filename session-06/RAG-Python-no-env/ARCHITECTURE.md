# Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                  H2 COMPACT — ADK ORCHESTRATOR HARNESS                    │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
                         ┌────────────────────┐
                         │    USER PROMPT     │
                         └─────────┬──────────┘
                                   │
                                   ▼
                    ┌────────────────────────────┐
                    │      ADK ORCHESTRATOR      │
                    │                            │
                    │ Intent + Context Routing   │
                    └─────────────┬──────────────┘
                                  │
               ┌──────────────────┼──────────────────┐
               │                  │                  │
               ▼                  ▼                  ▼
      GENERAL CONVERSATION   KNOWLEDGE / POLICY   ANALYTICAL DATA
               │                  │                  │
               ▼                  ▼                  ▼
        GEMINI RESPONSE      HYBRID RAG AGENT   TEXT-to-SQL AGENT
        (no tool call)             │                  │
                                  │                  ▼
                         ┌────────┴────────┐    SAFE PLACEHOLDER
                         │                 │    NOT_IMPLEMENTED_YET
                         ▼                 ▼
                   LEXICAL SIGNAL    VECTOR SIGNAL
                         │                 │
                         │          Vertex AI Gemini
                         │             Embeddings
                         │                 │
                         └────────┬────────┘
                                  ▼
                           HYBRID FUSION
                           40% lexical
                           60% semantic
                                  │
                                  ▼
                       BIGQUERY KNOWLEDGE STORE
                       chunks + stored embeddings
                                  │
                                  ▼
                       GROUNDED EVIDENCE + CITATION
                                  │
                                  ▼
                          GEMINI SYNTHESIS
```

## Design principle

The orchestrator chooses a **capability**, not a retrieval strategy. Hybrid RAG owns retrieval. This keeps the live architecture to two understandable routing levels:

1. **Intent router** — General vs Knowledge/RAG vs Text-to-SQL.
2. **Hybrid retrieval** — combine lexical precision and semantic recall.

There is no planner/worker/critic loop in this compact version.
