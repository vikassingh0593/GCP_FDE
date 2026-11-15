# Walkthrough notebooks: the whole system, function by function

Three notebooks call the **real functions** of this project one step at a time and show what each returns, so you can
follow a document from file to search index, and a question from the user to the answer. They are for learning
(and for rebuilding the same design elsewhere, e.g. on Databricks); the pipeline itself runs from the scripts in `src/`.

| Notebook | Follows | Code it walks through |
|---|---|---|
| `01_ingestion_walkthrough.ipynb` | one document (German label v4.2) from file to searchable chunks | `01_load_tables.py`, `02_parse.py`, `02a_check_parse.py`, `03_embed_and_load.py`, `04_create_index.py` |
| `02_query_walkthrough.ipynb` | one question through every step of `rag_runtime.answer()`, then `lookup`, `compare`, text-to-SQL | `rag_runtime.py`, `text2sql.py`, `policy.py` |
| `03_agent_walkthrough.ipynb` | one user message through the agent: patient check, router, tool limits, tools, verbatim relay; then a real conversation | `harness/medevidence_agent_vks/agent.py`, `harness/tools.py`, `harness/sql_agent.py`, `patient_check.py`, `escalation.py` |

Read them in this order. Each starts with a map of the file's functions (`functions(module)`), then one cell per step:
a short "what and why", the call, and its output. Each ends with the GCP service used and its Databricks equivalent.

## Run them

1. Once: `cd submission && source .venv/bin/activate && pip install -r requirements-notebooks.txt`
2. Open a notebook in VS Code and pick the kernel **Python 3.12 (submission/.venv)** (top right, "Select Kernel").
3. Run the cells from the top. The first cell loads `env.sh` for you (a notebook cannot `source` it).

## LIVE or offline

The first cell of each notebook has `LIVE = False`.

- **`LIVE = False` (default, free):** every Google Cloud call is replayed from the recordings in
  `tests/fixtures/runtime/`, the same ones the offline tests use, so you see real outputs without any cost. Only the
  questions already in the notebooks are recorded.
- **`LIVE = True`:** real calls (BigQuery, Vertex AI, Gemini): about one cent per question. Then you can change the
  questions. Notebook 1 only reads (it never writes); notebooks 2 and 3 write the usual log rows, tagged
  `run_tag = notebook`, so the health report counts them as test traffic, not real use. Notebook 3's conversation
  section needs LIVE, because the router itself is a Gemini call.

If a live cell says `Reauthentication is needed`, run `gcloud auth application-default login` in a terminal.

## Rebuilding it on Databricks (summary)

| Here | Databricks |
|---|---|
| Cloud Storage `raw/` | Unity Catalog volume |
| BigQuery tables, views, `chunks` | Delta tables and views |
| Document AI Layout Parser | `ai_parse_document`, or Docling / Unstructured in a job |
| Vertex AI embeddings | a Model Serving embedding endpoint |
| BigQuery hybrid `VECTOR_SEARCH` with SQL filters | Mosaic AI Vector Search (hybrid query, filters) |
| Vertex AI Ranking API | the Vector Search reranker, or a reranker on Model Serving |
| Gemini | a Foundation Model API / external-model endpoint |
| Check Grounding | an LLM judge (MLflow / Agent Evaluation) or a custom check |
| ADK agent + callbacks + `adk web` | Mosaic AI Agent Framework (MLflow agent, often LangGraph); AI Playground |
| `agent_log`, `pipeline_health`, `escalations` | Delta tables, MLflow tracing, inference tables |

What does not change: the Python logic between the service calls (registry filters before search, template tagging,
authority order, evidence cards, the citation / number / premise checks, the patient check's fail-closed rule, the
verbatim relay). Databricks product names are as of 2026; check the current documentation before building.
