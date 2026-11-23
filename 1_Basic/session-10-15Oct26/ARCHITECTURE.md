# Architecture — Semantic Ontology Retrieval

```text
Question
  |
  +--> Embedding search over ontology catalog
  |       Finds candidate concepts / relations / rules
  |
  +--> Symbolic ontology expansion
  |       Follows explicit relationships, hierarchy and semantic rules
  |
  +--> Relevant ontology subgraph
  |
  +--> Gemini Text-to-Cypher
  |
  +--> Neo4j instance graph
  |
  +--> Grounded answer
```

## Why this is not just vector schema RAG

Cosine similarity only answers: **what ontology elements sound relevant?**

The ontology answers: **how are those concepts legally and meaningfully connected?**

For `skill gap`, the rule explicitly connects `Project`, `Employee`, and `Skill` through `REQUIRES`, `WORKS_ON`, and `HAS_SKILL`. The LLM therefore receives a connected semantic subgraph rather than the complete ontology or an arbitrary list of nearest descriptions.
