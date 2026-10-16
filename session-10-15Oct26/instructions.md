# Hands-on Instructions

## 1. Setup
```bash
chmod +x setup.sh
./setup.sh
source .venv/bin/activate
source lab.env
```

## 2. Start Neo4j
```bash
docker compose up -d
```
Browser: `http://localhost:7474`  
User: `neo4j`  
Password: `ontology123`

## 3. Verify environment
```bash
python preflight.py
```

## 4. Inspect ontology and data
```bash
cat ontology/ontology.json
cat data/seed.json
```
`ontology.json` is the semantic model. `seed.json` is instance data.

## 5. Load instance graph
```bash
python graph/01_load_graph.py
```
In Neo4j Browser:
```cypher
MATCH (n)-[r]->(m) RETURN n,r,m;
```

## 6. Build ontology semantic index
This indexes ontology **objects, relationships and semantic rules**, not business rows.
```bash
python retrieval/01_build_ontology_index.py
```

## 7. Observe semantic discovery + ontology expansion
```bash
python retrieval/02_demo_retrieval.py "Which projects have skill gaps?"
```
Look at two outputs separately:
1. `SEMANTIC HITS` = cosine/embedding candidates.
2. `EXPANDED RELEVANT ONTOLOGY` = relationships/rules added by ontology traversal.

This distinction is the core of the lab.

## 8. Run ontology-retrieved Text-to-Cypher
```bash
python genai/text_to_cypher_retrieved.py "Which projects have skill gaps and what skills are missing?"
```
The program prints the exact ontology subgraph sent to Gemini. The full ontology is **not** placed in model context.

Try:
```bash
python genai/text_to_cypher_retrieved.py "Which critical risks threaten production go-live?"
```

## Understanding the Two Retrieval Programs

This hands-on separates **ontology retrieval** from the complete **ontology-aware Text-to-Cypher pipeline**.

---

### 1. Visualize Ontology Retrieval and Expansion

Run:

```bash
python retrieval/02_demo_retrieval.py \
  "Which projects have skill gaps?"
```

This program demonstrates how the relevant ontology is selected.

```text
User Question
     │
     ▼
┌──────────────────────────────┐
│ 1. Semantic Search           │
│                              │
│ Question Embedding           │
│        ↓                     │
│ Cosine Similarity            │
│        ↓                     │
│ Top-K Ontology Elements      │
└──────────────┬───────────────┘
               │
               │ Seed Concepts
               ▼
┌──────────────────────────────┐
│ 2. Ontology Expansion        │
│                              │
│ Traverse relationships       │
│ Apply semantic rules         │
│ Include connected concepts   │
└──────────────┬───────────────┘
               │
               ▼
      Relevant Ontology
          Subgraph
```

For example, semantic search may initially find:

```text
Project
Skill
SkillGap
```

Ontology traversal can then discover that understanding a skill gap also requires:

```text
Employee

Project  ──REQUIRES───> Skill
Employee ──HAS_SKILL──> Skill
Employee ──WORKS_ON───> Project
```

Therefore, **Top-K embedding search finds the entry points**, while **ontology traversal expands those entry points into a semantically meaningful subgraph**.

This reduces the risk of giving the LLM incomplete schema context simply because an important concept was not present in the Top-K embedding results.

> Important: Ontology expansion reduces retrieval incompleteness; it cannot compensate for an ontology that is itself incomplete or incorrectly modeled.

---

### 2. Run the Complete Ontology-Aware Text-to-Cypher Pipeline

Run:

```bash
python genai/text_to_cypher_retrieved.py \
  "Which critical risks threaten production go-live?"
```

This program internally performs the complete pipeline:

```text
Natural-Language Question
          │
          ▼
┌─────────────────────────┐
│ Semantic Retrieval      │
│ Embedding + Cosine      │
│ Top-K Candidates        │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ Ontology Expansion      │
│ Relationships + Rules   │
│ Connected Concepts      │
└────────────┬────────────┘
             ▼
     Relevant Ontology
         Subgraph
             │
             ▼
┌─────────────────────────┐
│ Gemini                  │
│ Question + ONLY         │
│ Relevant Ontology       │
└────────────┬────────────┘
             │
             ▼
       Generated Cypher
             │
             ▼
           Neo4j
             │
             ▼
      Matching Graph Facts
             │
             ▼
           Gemini
             │
             ▼
       Grounded Answer
```

The important difference from the earlier simple Text-to-Cypher approach is:

```text
Simple Lab

Entire Ontology
      ↓
     LLM
      ↓
    Cypher
```

versus:

```text
Production-Oriented Pattern

Question
   ↓
Semantic Retrieval
   ↓
Ontology Traversal
   ↓
Relevant Ontology Only
   ↓
LLM
   ↓
Cypher
```

The LLM therefore receives a **small, question-specific semantic subgraph** rather than the complete enterprise ontology.

---

### Key Takeaway

```text
Embeddings answer:

"What ontology concepts appear relevant to this question?"


Ontology traversal answers:

"What other concepts, relationships and rules are
semantically required to understand those concepts?"


Neo4j answers:

"What actual enterprise facts match this semantic structure?"


Gemini answers:

"How should those retrieved facts be explained to the user?"
```

This is what makes the solution **ontology-aware**, rather than simply performing vector search over schema descriptions.

## 9. Compare with plain schema RAG
Plain vector schema RAG:
```text
question -> nearest descriptions -> LLM
```
This lab:
```text
question -> nearest ontology elements -> ontology relationships/rules/hierarchy -> connected semantic subgraph -> LLM
```

## 10. Optional ADK agent
```bash
.venv/bin/adk web --port 8081
```
Open `http://127.0.0.1:8081` and select `agent`. Try: `What skill gaps does FDE-201 have?`

## 11. Cleanup
```bash
docker compose down
```
Delete data too:
```bash
docker compose down -v
```

## Production notes
- Use a managed/vector index rather than local JSON for a large ontology.
- Retrieve candidate concepts first, then perform bounded ontology graph expansion.
- Add authorization, query parsing/AST validation, query timeouts and row limits.
- Treat LLM-generated Cypher as untrusted input.
- Version and govern ontology changes.
