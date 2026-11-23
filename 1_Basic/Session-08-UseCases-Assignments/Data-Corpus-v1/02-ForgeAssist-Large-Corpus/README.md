# ForgeAssist Large Synthetic Corpus

Purpose-built synthetic corpus for the Tredence FDE production-RAG assignment.

## Scale target
The corpus is deliberately sized to produce **500+ chunks** under a typical ~256-token production-style chunking configuration. Actual counts depend on parser, OCR, overlap, table handling and parent-heading injection.

## Engineering traps
- exact identifiers E117 vs E171
- current safety bulletin overrides manual/notes
- image-only workorders require OCR
- parts and telemetry are structured sources
- unsafe technician notes are intentionally present
- 2-second SLA encourages conditional/parallel retrieval

## Important
Not every source should automatically be embedded. Participants are expected to choose between layout parsing, OCR, structured querying, live/tool access, exact search, vector search and hybrid retrieval.

All names, organizations, incidents, policies and operational facts are fictional and for training only.
