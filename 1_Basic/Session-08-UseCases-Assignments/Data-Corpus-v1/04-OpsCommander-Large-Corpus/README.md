# OpsCommander Large Synthetic Corpus

Purpose-built synthetic corpus for the Tredence FDE production-RAG assignment.

## Scale target
The corpus is deliberately sized to produce **500+ chunks** under a typical ~256-token production-style chunking configuration. Actual counts depend on parser, OCR, overlap, table handling and parent-heading injection.

## Engineering traps
- current vs obsolete runbooks
- historical similarity is not current causality
- logs/metrics/deployments/orders are live structured sources
- image-only legacy architecture pack requires OCR if used
- PAY-5037 exact identifier retrieval
- three-second SLA encourages parallel/conditional tools
- auto-remediation must not be authorized by model confidence

## Important
Not every source should automatically be embedded. Participants are expected to choose between layout parsing, OCR, structured querying, live/tool access, exact search, vector search and hybrid retrieval.

All names, organizations, incidents, policies and operational facts are fictional and for training only.
