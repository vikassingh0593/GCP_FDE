# RMIntelligence Large Synthetic Corpus

Purpose-built synthetic corpus for the Tredence FDE production-RAG assignment.

## Scale target
The corpus is deliberately sized to produce **500+ chunks** under a typical ~256-token production-style chunking configuration. Actual counts depend on parser, OCR, overlap, table handling and parent-heading injection.

## Engineering traps
- contract clause cross-references
- current vs superseded policy
- restricted BetaCorp evidence is semantically similar
- authorization must constrain retrieval
- scanned KYC requires OCR
- CRM/exposure data should be queried structurally
- policy and contract evidence must be combined

## Important
Not every source should automatically be embedded. Participants are expected to choose between layout parsing, OCR, structured querying, live/tool access, exact search, vector search and hybrid retrieval.

All names, organizations, incidents, policies and operational facts are fictional and for training only.
