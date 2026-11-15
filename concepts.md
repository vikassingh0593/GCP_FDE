# Concepts for building agentic AI tools

The concepts to keep in mind when building an agentic tool, in the order the tool is built:

ingestion → parsing → chunking → embeddings → vector storage → data governance → search → reranking → context → models → model gateway → answer generation → answer checks → agents → agent interoperability → text-to-SQL → knowledge graphs → orchestration → agent runtime → long-running and action agents → evaluation → responsible AI → security → platform security → operations → reliability → environments and delivery → FDE practice.

Every concept uses the same headings:

| Heading | What it holds |
|---|---|
| **Types and techniques** | the variants, each explained |
| **GCP tools** | the Google Cloud services and what each one does |
| **Key choices** | the decisions you make when designing |
| **Open source** | good open-source options |
| **Databricks** | the equivalent on Databricks |
| **Local → production** | how a local or lab set-up differs from production |
| **Keep in mind** | the lessons that prevent common mistakes |

Covers Sessions 1–19. Concepts from later sessions go into the matching section.

**BEYOND THE COURSE** marks enterprise concepts that the sessions did not cover, added as a reference. Whole sections carry the mark in their heading; single additions inside a course section say "(beyond the course)".

---

## 1. Ingestion

Getting source documents and their metadata into the system, and keeping them current.

**Types and techniques**
- **Batch ingestion:** load everything on a schedule (e.g. nightly). Simple, but a change waits for the next run.
- **Event-driven (incremental) ingestion:** each new or changed file triggers its own run. Needed when a document must be searchable within minutes.
- **Change detection by fingerprint:** a file hash (MD5) or modified time shows what changed, so only those files are processed again.
- **Source of truth for metadata:** status, version, country and effective dates come from the system that owns them (a document register), never from parsed text or from a model.
- **Provenance:** every piece keeps its source ID, URI, page, section and version, so an answer can cite it. The full chain (source → parsed unit → indexed unit → evidence → claim → citation) is called **grounding lineage**.
- **Quality gate:** checks after parsing and before indexing. A failing document is flagged or quarantined, never silently indexed.
- **Idempotent loads:** re-running a load gives the same result, with no duplicates (a staging table plus MERGE; a document's rows are replaced as one unit).
- **Verify searchable:** after loading, a real search must find the document. Loaded is not the same as findable.
- **Freshness pipeline:** CHANGE → DETECT → PARSE → CHUNK → EMBED → LOAD → VERIFY. Each stage has an SLA, failure detection, a retry and an escalation path.

**GCP tools**
- **Cloud Storage:** the landing zone for original files, with versioning and retention rules.
- **Eventarc:** fires an event when a file lands in a bucket.
- **Cloud Run:** a *service* runs ingestion per file; a *job* runs a batch.
- **Pub/Sub:** a queue between steps, with a dead-letter topic for failures.
- **Workflows / Cloud Composer (managed Airflow):** run multi-step pipelines with retries.
- **Dataflow:** large-scale batch or streaming processing.
- **BigQuery:** holds the document register, the chunks and the pipeline health records.
- **Managed RAG option: Vertex AI Search and Vertex AI RAG Engine.** These ingest, parse, chunk, embed and index files in one service, with connectors for Cloud Storage, Drive and other sources.

**Key choices**
- Build your own pipeline (full control over parsing, metadata and checks) or use a managed RAG service (faster to start, less control).
- Batch or event-driven, decided by the freshness SLA.
- Where the metadata comes from, and who owns it.
- Which failures block indexing (quarantine) and which only warn.
- How failures are retried and surfaced (dead-letter queue, a reconcile sweep, alerts).

**Open source**
- Orchestration: **Apache Airflow**, **Prefect**, **Dagster**.
- Processing: **Apache Beam** (the open-source SDK behind Dataflow).
- Loading: **LlamaIndex / LangChain** document loaders; **Unstructured** (loaders + partitioning).

**Databricks**
- Unity Catalog **volumes** for files.
- **Auto Loader** for incremental file ingestion, with file-arrival triggers.
- **Lakeflow Connect** for source connectors (e.g. SharePoint).
- **Lakeflow Declarative Pipelines** (formerly Delta Live Tables) and **Lakeflow Jobs** for pipelines; Delta tables with MERGE.
- Managed option: **Agent Bricks Knowledge Assistant**.

**Local → production**
- A manual upload and a script run by hand become: automatic export from the document management system when a document is approved → Eventarc → Cloud Run per file, plus a nightly reconcile job and alerts.

**Keep in mind**
- A healthy nightly pipeline still misses a same-day freshness SLA.
- Metadata from a model or from parsed text is a guess; metadata from the register is a fact.

---

## 2. Parsing

Turning a file (PDF, DOCX, scan) into structured text: headings, paragraphs, tables, lists, reading order and pages.

**Types and techniques**
- **Plain text extraction:** fast, but loses headings, tables and pages. Fine only for simple prose.
- **Layout-aware parsing:** detects blocks (heading, paragraph, table, list) and reading order, and keeps the hierarchy.
- **OCR:** reads text from scanned pages or images. Quality depends on the scan.
- **Table structure extraction:** returns rows, columns and header cells, not just the text.
- **Audio and video (beyond the course):** speech is transcribed with timestamps, video is split into scenes with transcripts and frame descriptions; every piece keeps its time range as provenance (Speech-to-Text, Video Intelligence API, Gemini).
- **Figure handling:** captions, plus optional model-written descriptions of images. Label that text as generated so it is never cited as the document's own words.
- **Field extraction:** pulls named fields (invoice number, date) into a schema.
- **Parsing is not chunking:** parsing recovers the structure; chunking cuts it into retrievable pieces.

**GCP tools**
- **Document AI Layout Parser:** layout blocks, tables, heading hierarchy and layout-aware chunks. Online processing for small files, batch for large ones.
- **Enterprise Document OCR:** OCR with a quality score per page and the defects it found (blurry, dark, …).
- **Form Parser / Custom Extractor:** key-value pairs and fields extracted to a schema.
- **Gemini (multimodal):** reads a page image and returns structured JSON. Useful for unusual layouts; the output must be checked.
- **Model Armor:** screens documents for hidden instructions and malicious links before they enter the system.

**Key choices**
- A managed parser, an open-source parser, or Gemini reading page images.
- Pin the processor version, and test before upgrading: a new version can change the chunks.
- Cache results by file fingerprint plus processor version, so an unchanged file is never parsed twice.
- What to check after parsing: page count, OCR quality, junk characters, tables intact, faithfulness to the file's own text.

**Open source**
- **Docling:** layout and tables, runs locally.
- **Unstructured:** partitions many file formats.
- **Marker:** PDF → Markdown.
- **PyMuPDF / pdfplumber:** text with positions.
- **Apache Tika:** text and metadata from many formats.
- **Tesseract:** OCR.

**Databricks**
- The **`ai_parse_document`** SQL function (layout elements, page metadata, optional AI descriptions of figures), run over files in volumes.
- Or open-source parsers in notebooks and pipelines.

**Local → production**
- An open-source parser on a laptop without OCR becomes a managed parser with OCR, batch mode and quality scores; low-quality pages go to human review.

**Keep in mind**
- Turning a PDF into plain text destroys tables and headings. This is one of the most common root causes of wrong answers.
- Inspect the parsed output before you embed it.

---

## 3. Chunking

Cutting parsed documents into pieces small enough to match a question and large enough to hold a complete statement.

**Types and techniques**
- **Fixed-size / recursive:** split every N tokens. A recursive splitter tries paragraph breaks first, then sentences, then words. A baseline for plain prose.
- **Heading-aware (structure-aware):** split at headings and paragraph ends, never across a heading. For policies, manuals and product labels.
- **Semantic chunking:** split where the topic changes, detected by a drop in similarity between neighboring sentences.
- **Table-aware:** a table stays whole, because a row without its header is meaningless. A long table is split by rows, with the header repeated in each piece.
- **Code-aware:** split by function or class.
- **Overlap:** repeat the last sentences of one chunk at the start of the next, so a statement cut in half can still be found. The cost is duplicate text.
- **Contextualized chunks:** add the missing context before embedding, either the heading path ("Dosage › Renal impairment") or a generated sentence. This is the idea behind "Contextual Retrieval".
- **Parent-child (small-to-big):** search small chunks for precision, then give the model the larger parent section.
- **Neighbor (window) expansion:** add chunks N−1 and N+1 at answer time.
- **Template removal and de-duplication:** boilerplate repeated in many documents, and copies of the same text, crowd out real content. Tag them and keep them out of search.

**GCP tools**
- **Document AI Layout Parser:** chunk size and an "include ancestor headings" option.
- **Vertex AI RAG Engine / Vertex AI Search:** chunk size and overlap settings in the managed services.

**Key choices**
- The unit of evidence that must survive intact (a table, a warning box, a clause), per document type.
- Chunk size in tokens. Too small loses meaning; too big dilutes the match and wastes context.
- Overlap, or heading injection (which avoids duplicates).
- Whether to separate the unit you search from the unit you answer from (parent-child, neighbors).

**Open source**
- **LangChain text splitters** (Recursive, MarkdownHeader).
- **LlamaIndex node parsers** (Sentence, Semantic, Hierarchical).
- **Docling HybridChunker**, **Chonkie**.

**Databricks**
- No dedicated managed chunker: chunk in Python (LangChain or LlamaIndex) inside notebooks or Lakeflow pipelines, using the `ai_parse_document` output.
- Agent Bricks Knowledge Assistant chunks automatically.

**Local → production**
- A chunking script whose output you check by hand becomes the same logic in the pipeline, with automated checks and sampled human review for new document types.

**Keep in mind**
- Ask "what unit must survive intact?", not only "what chunk size?".
- One chunk size for every source is an anti-pattern.

---

## 4. Embeddings

Turning text into a vector (a list of numbers), so that texts with similar meaning sit close together.

**Types and techniques**
- **Token embeddings vs text embeddings:** a model's first layer turns each token into a vector; a text-embedding model gives one vector for a whole text. Retrieval uses text embeddings.
- **Dense embeddings:** every number carries meaning ("kidney" ≈ "renal").
- **Sparse embeddings:** mostly zeros, roughly one slot per word (e.g. SPLADE). They capture exact terms and are used for hybrid search.
- **Multimodal embeddings:** images and text in the same vector space.
- **Task types:** separate settings for documents and for queries, because a question looks different from a passage. Classification, clustering and similarity have their own task types too.
- **Dimensionality:** fewer numbers (e.g. 768 instead of 3,072) means less storage and faster search, at a small quality cost. Matryoshka-trained models can be truncated safely.
- **Similarity measures:** cosine (the angle between vectors), dot product, Euclidean distance. With normalized vectors, cosine equals the dot product.

**GCP tools**
- **Vertex AI embeddings:**
  - `gemini-embedding-001`, with task types and `output_dimensionality`;
  - `text-embedding-005`;
  - multimodal embeddings;
  - batch prediction for large volumes.
- **BigQuery `AI.EMBED` / `ML.GENERATE_EMBEDDING`:** embed inside SQL, without Python.
- **Vertex AI Model Garden:** open embedding models you can deploy on Vertex AI.

**Key choices**
- The model (quality, languages, cost, retirement date) and the number of dimensions.
- Embed in Python (control over caching and retries) or in SQL (bulk work inside the warehouse).
- Cache by a hash of text + model, so only new or changed text is embedded.
- One model per index: never compare vectors from two models. When the model changes, re-embed everything into a parallel copy and switch once it is tested (blue/green).

**Open source**
- Models: **sentence-transformers**, **BGE** (including bge-m3, which gives dense and sparse vectors), **E5**, **GTE**, **Nomic Embed**.
- Serving locally: Hugging Face **TEI**, **Ollama**.

**Databricks**
- **Foundation Model APIs** embedding endpoints (e.g. GTE, BGE), plus external models through Model Serving.
- **Vector Search managed embeddings:** vectors computed automatically from a column of a Delta table.
- `ai_query` for batch embedding in SQL.

**Local → production**
- A local sentence-transformers model becomes a managed embedding API (no GPUs to run), with batch embedding for volume.

**Keep in mind**
- Similar is not the same as correct: semantic similarity is not evidence quality.
- Embedding questions with the document task type quietly lowers recall.

---

## 5. Vector storage and indexing

Where vectors live, next to their text and metadata, and how they are searched quickly.

**Types and techniques**
- **Exact (brute-force) search:** compare the question with every vector. Perfect recall; fine for small tables.
- **Approximate nearest neighbor (ANN) index:** finds near-best matches without scanning everything. Common types:
  - **IVF:** groups vectors into clusters and searches only the closest clusters;
  - **TreeAH / ScaNN:** Google's tree plus compression;
  - **HNSW:** a graph of neighbors, common in open-source stores.
- **Recall vs latency:** an ANN index trades a little recall for speed, so measure its recall against exact search.
- **Stored (pre-filter) columns:** filter columns kept inside the index, so filtering happens before the search. Otherwise filtering happens afterwards and can return fewer results than asked for.
- **Kinds of vector store:** a data warehouse (BigQuery), a database with a vector extension (Postgres + pgvector), a dedicated vector database, or a managed RAG corpus.

**GCP tools**
- **BigQuery:** vectors in an array column beside text and metadata; `VECTOR_SEARCH`; `CREATE VECTOR INDEX` (IVF or TreeAH) with `STORING` columns; partitioned and clustered tables.
- **Vertex AI Vector Search:** a dedicated ANN service (ScaNN) for millisecond latency at very large scale, with filters and hybrid (dense + sparse) search.
- **AlloyDB / Cloud SQL for PostgreSQL:** pgvector, so vectors sit next to transactional data. AlloyDB adds a ScaNN index.
- **Vertex AI RAG Engine:** a managed corpus with a choice of vector back-ends.
- Firestore and Spanner also offer vector search for application data.

**Key choices**
- The store: a warehouse (analytics and SQL filters), an operational database, or a dedicated vector service. Decided by scale, latency and where the metadata lives.
- Exact search or an index; the index type; which filter columns to store.
- The load pattern: staging plus MERGE, so re-runs never duplicate.
- Views computed at query time (e.g. "current version"), so a status never goes stale.

**Open source**
- **pgvector** (Postgres), **FAISS** (a library), **Qdrant**, **Weaviate**, **Milvus**, **Chroma** (local development), **LanceDB**, **OpenSearch / Elasticsearch** (kNN + BM25).

**Databricks**
- **Mosaic AI Vector Search:**
  - a Delta Sync index (kept in sync with a Delta table) or a Direct Vector Access index;
  - standard and storage-optimized endpoints;
  - filters; data governed in Unity Catalog.

**Local → production**
- Exact search on a small table becomes an ANN index with stored filter columns, recall-tested, on partitioned and clustered tables.

**Keep in mind**
- Adding an index without checking recall can silently drop the right answer.

---

## 6. Data governance and lifecycle · BEYOND THE COURSE

Knowing where data came from, what it may be used for and how long it is kept, and removing it everywhere when required.

**Types and techniques**
- **Lineage:** each piece is traceable from the source file → parsed unit → chunk → embedding → index → the answer that cited it. Needed for audit, and to find every answer that used a document that is now withdrawn.
- **Data contracts:** an agreed schema, meaning and quality rules between the source owner and your pipeline. A breaking change stops the pipeline instead of silently changing answers.
- **Classification and tags:** sensitivity labels (public, internal, confidential, personal data) on documents and columns. Tags drive filters, masking and retention.
- **Retention:** how long raw files, chunks, logs, traces and caches are kept, including legal holds.
- **Deletion ("right to be forgotten"):** a deleted or withdrawn document must disappear from **every** copy: landing storage, parse cache, chunks, vector index, facts tables, caches, evaluation sets and (within their window) backups.
- **Withdrawn vs superseded:** a superseded version stays for "what applied then" questions; a withdrawn or recalled one leaves answers immediately.
- **Purpose limitation:** data is used only for the purpose it was collected for.

**GCP tools**
- **Knowledge Catalog** (formerly Dataplex Universal Catalog): lineage, tags (aspects), data quality, business glossary.
- **Sensitive Data Protection:** discovers and classifies sensitive data across BigQuery and Cloud Storage.
- **Cloud Storage:** retention policies, bucket lock, object lifecycle rules.
- **BigQuery:** table and partition expiration, policy tags (column-level security), time-travel window.

**Key choices**
- The deletion deadline, and an inventory of every place a document is copied.
- Soft delete (hidden) or hard delete (physically removed), per data class.
- Retention per data class.
- Who owns each data contract.

**Open source**
- Lineage and catalogs: **OpenLineage** (+ Marquez), **DataHub**, **Apache Atlas**.
- Data quality and contracts: **Great Expectations**, **Soda**.

**Databricks**
- **Unity Catalog:** lineage, tags, row filters and column masks.
- Delta `DELETE` + `VACUUM` to remove data physically; Vector Search Delta Sync carries deletes into the index.

**Local → production**
- Files deleted by hand become a deletion workflow that removes a document from every store and records proof that it did.

**Keep in mind**
- A document is not deleted until it is gone from the vector index and the caches too.
- Withdrawn is not the same as superseded.

---

## 7. Search (retrieval)

Finding the pieces of evidence that can answer a question.

**Types and techniques**
- **Lexical (keyword) search:** matches exact words, scored BM25-style (rare words count more). Best for IDs, clause numbers, codes, doses and rare names. Misses paraphrases.
- **Semantic (dense vector) search:** matches meaning ("products disappearing from shelf" ≈ "stockout"). Weak on exact IDs, versions and numbers.
- **Hybrid search:** runs both and fuses the results. The usual default for enterprise documents.
- **Reciprocal Rank Fusion (RRF):** fuses by rank position, not score: Σ 1/(k + rank), with k ≈ 60. Robust, because word scores and vector scores are on different scales. A fused score is not a similarity, so never put a threshold on it.
- **Weighted / dynamic fusion:** final = α·semantic + β·lexical. The weights can depend on the question (an ID → more lexical). Needs measurement before you rely on it.
- **Metadata filtering (hard filters):** mandatory rules applied before ranking: product, status, country, date, user access. A governance control, not just a relevance aid.
- **Point-in-time (as-of) search:** filter by valid-from and valid-to dates to answer "what applied on date X?".
- **Query transformation:**
  - *rewriting:* turn the user's words into the corpus's words (keep and log the original);
  - *multi-query:* several searches for the same need, fused together;
  - *decomposition:* split a multi-part question into different needs;
  - *HyDE:* search with a hypothetical answer (never cite it).
- **Retrieval routing:** exact ID → lexical, concept → semantic, mixed → hybrid, metric → SQL, relationships → graph.
- **Multimodal retrieval (beyond the course):** search images and video frames with multimodal embeddings, or search their generated descriptions and transcripts as text (Vertex AI multimodal embeddings).
- **Graph-assisted retrieval:** follow relationships between entities instead of matching text. Covered in full under Knowledge graphs and Text-to-Cypher (§17).
- **Candidate pool (top-K):** retrieve generously (e.g. 20–100) for recall, then rerank down to a few.

**GCP tools**
- **BigQuery `VECTOR_SEARCH`:** semantic search, plus hybrid mode with `lexical_search_columns`. Filters go in a SQL `WHERE`, with values passed as query parameters.
- **BigQuery `SEARCH()` + search index:** lexical search on text columns.
- **Vertex AI Vector Search:** ANN with filters and hybrid (dense + sparse) search.
- **Vertex AI Search:** fully managed search (hybrid, ranking, filters) over its own data stores.
- **Vertex AI RAG Engine:** managed retrieval over a corpus.

**Key choices**
- Which search types your questions need. Look at real questions: IDs, paraphrases, or both?
- Filters applied before the search, built from trusted metadata, with values passed as parameters, never pasted into the SQL text.
- The size of the candidate pool (top-K).
- The fusion method: RRF by default, weights only if measured.
- Whether query transformation is worth its cost and risk.

**Open source**
- Search engines: **Elasticsearch / OpenSearch** (BM25 + kNN + hybrid), **rank_bm25** (Python), **Tantivy**.
- Hybrid in **Qdrant**, **Weaviate** and **Milvus**; **SPLADE** sparse vectors.
- Frameworks: **LlamaIndex**, **LangChain** and **Haystack** retrievers.

**Databricks**
- **Mosaic AI Vector Search:** `query_type="HYBRID"` (keyword + vector), filters, and the `vector_search()` SQL function.

**Local → production**
- Exact search with no per-user filters becomes an ANN index with stored filter columns, plus each user's access rights as filters.

**Keep in mind**
- Raising top-K until the answer appears is an anti-pattern. Find out why the answer ranked low.
- Exact identifiers should not be forced through semantic search.
- A similarity score is not a confidence score.

---

## 8. Reranking

Re-ordering the candidate pool so the passage that actually answers the question comes first.

**Types and techniques**
- **Bi-encoder (first stage):** the question and each passage are embedded separately. Fast; used for search.
- **Cross-encoder reranker:** reads the question and a passage together. Slower and much more accurate, so it runs only on the top 20–100.
- **LLM as reranker:** a general model orders the candidates (returns IDs as JSON). Flexible, but slower, costlier and less consistent.
- **Late interaction (ColBERT):** matches token by token; its cost sits between the other two.
- **Authority ordering (after reranking):** relevance is not authority. Code orders the results by source type and status from metadata (e.g. safety bulletin › product label › study; approved › superseded).

**GCP tools**
- **Vertex AI Ranking API** (part of Discovery Engine): a managed cross-encoder ranker (the `semantic-ranker-…` models) that returns a score per passage.
- **Gemini:** an LLM reranker, when a custom judgment is needed.
- **Vertex AI RAG Engine / Vertex AI Search:** built-in ranking options.

**Key choices**
- How many candidates go in (e.g. 20–50) and how many come out (e.g. 5).
- A managed ranker or an LLM ranker (measure both).
- Authority rules agreed with the customer and applied in code.

**Open source**
- **sentence-transformers CrossEncoder** (ms-marco models), **BAAI bge-reranker**, **ColBERT / RAGatouille**, **FlashRank**.

**Databricks**
- The **Vector Search reranker** (`columns_to_rerank`) on query results.

**Local → production**
- An LLM reranker in a lab becomes a managed ranker: faster, cheaper, with consistent scores.

**Keep in mind**
- The first stage is for recall, reranking is for precision. Spend the expensive model only on the small set.
- Adding reranking before you have measured retrieval is an anti-pattern.

---

## 9. Context building

Deciding what reaches the model, in what form and in what order.

**Types and techniques**
- **Evidence cards:** numbered passages, each with a header written by code (document, version, status, page, role), so the model can cite [E1], [E2].
- **Roles / labels:** each piece is marked as local guidance, supporting evidence or historical, from metadata.
- **Context budget:** a cap on characters or tokens. More context is not better: it adds cost and latency and distracts the model.
- **Sufficiency check (refusal-aware retrieval):** before generating, check that the evidence is enough (e.g. a question about one country needs a document for that country). If it isn't, abstain without calling the model.
- **Context compression:** trim passages down to the relevant sentences. This risks removing qualifications and exceptions, so keep a pointer to the original.
- **Parent / neighbor expansion:** add the surrounding text when a chunk lacks context.
- **Context caching:** reuse a long prompt prefix that doesn't change (instructions, a catalog of documents) to save cost and latency.

**GCP tools**
- **Gemini context caching** (implicit and explicit).
- Context building itself is your own code.

**Key choices**
- Which metadata the model sees in each card header.
- The budget and the ordering (authority first).
- The sufficiency rule for abstaining.
- Keep per-turn content out of fixed instructions, so the prefix can be cached.

**Open source**
- **LlamaIndex** node postprocessors, **LangChain** document compressors, **LLMLingua** (prompt compression).

**Databricks**
- Built in your agent code (Agent Framework); Vector Search returns the metadata columns for the headers.

**Local → production**
- Same logic. Production adds per-user filtering of what may enter the context.

**Keep in mind**
- A large context window does not mean you should fill it.
- The model can only cite what it sees, and headers written by code make its citations checkable.

---

## 10. LLM basics (models)

How models read and write text, and how to choose one.

**Types and techniques**
- **Tokens:** models read tokens (pieces of words), each with an ID. BPE builds the vocabulary by merging frequent character pairs, so rare words split ("Patil" → "Pat" + "il"). Context limits, cost and latency are all counted in tokens.
- **Generation loop:** tokens → IDs → vectors → model → next token → decode, one token at a time. That is why long outputs are slow, and why output tokens cost more than input tokens.
- **Context window:** how many tokens fit in one call: instructions + evidence + history + the answer.
- **Model families and sizes:** tiers such as Flash-Lite / Flash / Pro trade cost and speed against reasoning. Open models include Gemma, Llama, Mistral and Qwen.
- **Temperature:** controls randomness; 0–0.1 for repeatable tasks. Even at 0, output is not fully deterministic.
- **Thinking (reasoning) budget:** hidden reasoning before the answer. 0 (off) for simple classification; more for planning.
- **Model selection by workflow:** weigh modality, reasoning, context, latency, quality, throughput and economics (cost per successful task). The flow: workflow → modality → quality → context → latency → platform and security → cost → candidates → evaluate → defend the choice.
- **Mixed architecture:** a stronger model plans, a faster model works, deterministic code validates.
- **Model lifecycle:** every model version has a retirement date.

**GCP tools**
- **Gemini on Vertex AI** (the `google-genai` SDK): generation, token counting, usage metadata, thinking settings, regional or global endpoints.
- **Vertex AI Model Garden:** Google, partner and open models.
- **Provisioned Throughput:** reserved model capacity.

**Key choices**
- One model per task (router, writer, classifier), chosen by evaluation, not by name.
- Temperature and thinking set per task.
- Track retirement dates, and keep model names only in configuration.

**Open source**
- Tokenizers and models: **Hugging Face transformers / tokenizers**, **tiktoken**.
- Serving: **vLLM**, **Ollama**, **llama.cpp**.
- Open models: **Gemma**, **Llama**, **Mistral**, **Qwen**.

**Databricks**
- **Foundation Model APIs:** pay-per-token or provisioned throughput.
- **Model Serving:** custom and external models.
- **AI Gateway:** rate limits, usage tracking and guardrails.

**Local → production**
- A local open model, or a third-party model router, becomes the managed model API, accessed with a service account and backed by reserved capacity.

**Keep in mind**
- Don't pay for reasoning the task doesn't use.
- Re-run the evaluation before any model switch.

---

## 11. Model gateway, routing and customization · BEYOND THE COURSE

One controlled entry point for all model calls, and when to change the model itself rather than its inputs.

**Types and techniques**
- **LLM gateway:** a single proxy in front of every model call: authentication, per-team quotas, logging, cost attribution, safety screening, key management.
- **Model routing:** pick the model per request: a cheap model for simple tasks, a stronger one for hard ones, a regional one for residency.
- **Fallback and failover:** if a model is busy, down or retired, switch to an approved backup model or region that has already passed the evaluation.
- **Semantic caching:** reuse an answer when a new question *means* the same as a cached one (embedding similarity above a threshold). Saves cost, but risky for regulated or personal answers: the key must include the corpus version and the user's access rights, the lifetime must be short, and per-user data is never shared.
- **Fine-tuning (supervised tuning):** train the model on examples to change *behavior*: output format, tone, a narrow classification, domain wording. Not for facts that change; those belong in RAG.
- **Distillation:** train a smaller, cheaper model to imitate a larger one on your task.
- **Prompting vs RAG vs fine-tuning:** start with prompting; RAG for changing knowledge that needs citations; fine-tuning for stable behavior, or for cost and latency at scale.
- **Batch inference:** non-interactive bulk jobs at lower cost.

**GCP tools**
- **Vertex AI Model Garden:** Google, partner and open models.
- **Vertex AI tuning:** supervised fine-tuning and distillation for Gemini.
- **Vertex AI batch prediction:** bulk jobs.
- **Apigee as an AI gateway:** token quotas, Model Armor integration and semantic-caching policies (check the current policy list).
- **Provisioned Throughput** and the Gemini global endpoint for capacity.

**Key choices**
- Which task uses which model, and the approved fallback list.
- Which answer types may be cached at all.
- Whether to tune, decided only by a measured gain on the evaluation set.

**Open source**
- Gateways: **LiteLLM** proxy (routing, fallbacks, budgets), **Portkey** gateway.
- Semantic caches: **GPTCache**, **RedisVL**.
- Fine-tuning: Hugging Face **TRL** / **PEFT** (LoRA); serving with **vLLM**.

**Databricks**
- **Mosaic AI Gateway:** rate limits, fallbacks, traffic splitting, usage tracking, guardrails.
- **Foundation Model Fine-tuning**; batch inference with `ai_query`.

**Local → production**
- Direct SDK calls to one model become calls through a gateway, with routing, a tested fallback and cost tracking per team.

**Keep in mind**
- A fallback model is a different model: evaluate it before you need it.
- Cache only what is safe to share between users.

---

## 12. Answer generation

Writing the answer from the evidence only.

**Types and techniques**
- **Prompt patterns:**
  - *zero-shot:* rules, no examples;
  - *few-shot:* a few examples, when the boundary is easier to show than to describe (they cost context);
  - *rules + context:* instructions kept separate from evidence (ROLE / RULES / CONTEXT / TASK).
- **System instructions:** fixed rules the model receives on every call.
- **Structured output:** JSON that matches a schema (Pydantic or a dict) whenever code reads the result: the answer, citations, claims, missing items.
- **Grounded generation contract:** answer only from the supplied evidence, cite every statement, abstain when evidence is missing.
- **Citations:** a card ID after every statement. Code checks each one and writes the source list itself.
- **Abstention:** "I don't have this", with an offer to route the question. A correct answer, not a failure.
- **Text written by code:** sources, fixed notes and refusals come from code, not from the model.
- **Built-in grounding:** Gemini can ground its answer on Google Search or on your own data store (Vertex AI Search, RAG Engine).

**GCP tools**
- **Gemini on Vertex AI:** system instructions, `response_schema`, temperature, thinking settings.
- **Gemini grounding** on Vertex AI Search, RAG Engine or Google Search.
- **Vertex AI Studio:** try prompts and save them.

**Key choices**
- Free text or JSON: JSON whenever code checks or assembles the reply.
- What the model writes and what code writes.
- Prompt versioning (e.g. a hash of the rules), so tests and recorded responses expire when the rules change.

**Open source**
- Structured output: **Pydantic**, **Instructor**, **Outlines**.
- Prompts: **LangChain** / **LlamaIndex** prompt templates; **DSPy** (prompt optimization).

**Databricks**
- Foundation Model APIs with structured outputs (`response_format`).
- The **MLflow Prompt Registry** for versioned prompts.

**Local → production**
- Same, with prompts version-controlled and reviewed like code.

**Keep in mind**
- Valid JSON is not a correct answer: syntactic validity ≠ semantic reliability.
- The user should see only checked text. Never let an agent reword a checked answer.

---

## 13. Answer checks (verification)

Checking every AI output against something that is not AI, before the user sees it.

**Types and techniques**
- **Citation check:** every cited source exists and was part of the evidence.
- **Number check:** every number in the answer appears in the cited evidence.
- **Premise check:** if the user states a wrong value, code says "no" and gives the right one.
- **Claim check:** the model lists each claim (value, source, row, column), and code checks the value is in that exact table cell.
- **Grounding score:** a service scores how well each claim is supported (0–1). Below a threshold, the answer is blocked.
- **LLM-as-judge:** a second model grades faithfulness or relevance. Useful in evaluation, but it is an estimate, not proof.
- **Repair loop:** the model proposes → code verifies → the model repairs once, given the checker's message → everything is checked again → a second failure is blocked.
- **Fail closed:** when a check cannot run, block rather than pass.
- **Verbatim relay:** the agent passes the checked text on word for word.

**GCP tools**
- **Vertex AI Check Grounding API:** a support score per claim, against the facts you give it.
- **Vertex AI Gen AI evaluation service:** groundedness and other metrics, model-based and computed.
- **Model Armor:** screens responses for sensitive data and unsafe content.

**Key choices**
- Which checks are code (exact) and which are model-based (estimates).
- The grounding threshold, tuned on the evaluation set.
- How many repair tries to allow (each one adds latency).

**Open source**
- **Guardrails AI** (validators), **NeMo Guardrails**, and the faithfulness metrics in **Ragas** / **DeepEval**.

**Databricks**
- **MLflow 3** judges (groundedness, correctness, safety, custom guidelines) for evaluation and monitoring.
- **AI Gateway** guardrails (PII, safety) on serving endpoints.

**Local → production**
- The same checks. Production extends the claim check to values in running text, and monitors how often answers are blocked.

**Keep in mind**
- Check every AI output against something that is not AI.
- A grounding score is an estimate; exact checks (table cells, numbers) are proof.

---

## 14. Agents and tools

A model that decides which tools to call to complete a task.

**Types and techniques**
- **Function calling:** the model returns a function name plus arguments as JSON; your code runs the function and returns the result; the model writes the reply. The model never runs code itself. One response can contain **several calls** (parallel function calling), e.g. "check order X and the stock of item Y".
- **Model-visible tool contract:** the model never sees your code. It sees only a declaration built from the function's name, docstring, parameter types and schema. Print the declaration to see exactly what the model reads (`FunctionDeclaration.from_callable`).
- **Automatic vs manual calling:** the SDK can run Python tools automatically. Turn that off to run the loop yourself, so code can validate and authorize every call before it runs. Frameworks such as ADK run this loop for you, with callbacks.
- **Function-calling modes:**
  - **AUTO:** the model chooses between text and a tool;
  - **ANY:** it must call a tool, optionally from an allowed list;
  - **NONE:** text only, tools switched off;
  - **VALIDATED:** text, or a tool call that matches the schema.

  Use ANY to force a tool (e.g. an extraction or routing step), and NONE when a step must not take any action.
- **Function tools:** plain Python functions. The signature and docstring become the tool description the model reads.
- **Agent:** a model + an instruction + tools (an `LlmAgent` in ADK).
- **ADK runtime pieces:**
  - **App:** the application container (the root agent plus app-wide plugins).
  - **Runner:** the execution engine. It loads the session, calls the model, runs the tools, fires callbacks and plugins, streams events and saves the history. It executes; it never decides. The root agent orchestrates.
  - **Invocation:** one user message through to the final answer. ADK keeps an **InvocationContext** for it (the current agent, the session, the invocation ID). A session holds many invocations.
  - **Events:** what the Runner streams while it works: model text, tool calls, tool results.
  - **ToolContext / CallbackContext:** what a tool or callback can see: session state, the current call's ID.
- **Three kinds of memory:**
  - **Session history:** the conversation so far. A follow-up works because the Runner loads this history and sends it with the new message.
  - **Session state:** key-value pairs for this conversation, read and written by tools and callbacks.
  - **Long-term memory:** remembered across conversations (e.g. Memory Bank). Only where it is really needed; old remembered answers can be out of date.
- **State scopes:** a key's prefix decides how long it lives and who sees it:
  - no prefix: this session only (`current_case`);
  - `user:`: all of that user's sessions (`user:preferred_region`);
  - `app:`: everyone using the app (`app:lab_topic`);
  - `temp:`: the current invocation only, never saved (`temp:last_state_tool`).

  A wrong prefix such as `users:` raises no error: ADK treats it as plain session state, so the value silently stops carrying across sessions.
- **Instruction placeholders:** `{user:name?}` in an instruction is filled from state before each model call. The `?` makes it optional; without it, a missing key raises a `KeyError`.
- **State vs memory:** state reaches the prompt automatically. Memory doesn't: the agent has to search it with the `load_memory` tool, and it holds only sessions that code saved with `add_session_to_memory`.
- **Identification vs authentication:** an email typed into a form identifies a user; it doesn't prove who they are. A salted hash of the email gives a stable `user_id` with no personal data in it, but only a real sign-in authenticates.
- **Serving an agent:** one long-lived Runner and shared services per process, with a thin API in front (identify, create session, chat, save to memory). Every session lookup uses both `user_id` and `session_id`, and sensitive state is masked before it reaches a browser.
- **Callbacks / hooks:** code that runs at fixed points of each turn (before the agent, before a tool, after the model, on an error), for rules that must always hold. Details in the agent runtime concept (§19).
- **Tool limits:** cap tool calls per turn and tries per request, in code.
- **Tool result contract:** every tool returns the same shape (`status`, `code`, `retryable`, `data`), so the agent and runtime can tell `NOT_FOUND`, `DEPENDENCY_UNAVAILABLE` and `ACCESS_DENIED` apart.
- **Production tool contract:** for each tool, write down its purpose, input and output schemas, source of truth, data freshness, timeout, retry policy, idempotency, authorization scope, error codes, cost and rate limit, sensitive fields and audit needs.
- **Read tools vs action tools:**
  - a read tool only fetches;
  - an action tool (revoke, update, send) changes something and needs human approval, or stays out of the agent.

  Autonomy grows in steps: investigate → recommend with one-click approval → automatic only for narrow, clear-cut cases, with an undo path.
- **Concurrency:** allow one active request per session (disable sending in the UI, or lock or queue per session). Different sessions can run in parallel.
- **Agent definition:** in code (needed for callbacks and tests) or in YAML.

**GCP tools**
- **Gemini API (`google-genai`):** `tools=[...]`, `tool_config` modes, `automatic_function_calling`, `FunctionDeclaration.from_callable`.
- **Agent Development Kit (ADK):** an open-source framework with agents, tools, callbacks, plugins, sessions, the `adk web` development UI (with traces), `adk eval`, and a confirmation step before a tool runs.
- **Vertex AI Agent Engine:** a managed runtime for agents, with managed sessions and Memory Bank.
- **Cloud Run:** hosts an agent as a container.
- **Session services:**
  - `InMemorySessionService`: development only. Sessions are lost on restart, not shared between instances and not safe under concurrency.
  - `DatabaseSessionService`: your own database (Cloud SQL / AlloyDB).
  - `VertexAiSessionService`: managed by Agent Engine. The app name must be the numeric engine ID or the full resource name, unless the service was given an engine ID.
  - `adk web` keeps its sessions in a local SQLite file.
- **Memory services:**
  - `InMemoryMemoryService`: prototypes only. It matches keywords, not meaning, and is lost on restart.
  - `VertexAiMemoryBankService`: Memory Bank on Agent Engine, for production.

**Key choices**
- What each tool may do (read-only by default), with every argument validated in code.
- Which tools are actions, and who approves them.
- Put every safety rule inside tools or callbacks, so a wrong tool choice is unhelpful but never unsafe.
- Where sessions and memory are stored, and whether long-term memory is wanted at all.
- Which store each fact belongs in: ask how long it should live, and who should see it.
- When a session is saved to memory, and what may be remembered.
- One active request per session.
- Retries, plus a fixed fallback message when the model is busy.

**Open source**
- Frameworks: **ADK** itself, **LangGraph**, **LlamaIndex agents**, **CrewAI**, **AutoGen / AG2**, **OpenAI Agents SDK**, **smolagents**.
- **LiteLLM:** one API for many model providers.
- The function-calling modes exist in OpenAI-compatible APIs as `tool_choice` (`auto` / `required` / `none`).

**Databricks**
- **Foundation Model APIs** support function calling (OpenAI-compatible `tools` / `tool_choice`).
- **Mosaic AI Agent Framework:** write agents in Python (LangGraph, OpenAI SDK and others); deploy on **Databricks Apps** or Model Serving.
- **Unity Catalog functions** as governed tools.
- Agent memory in **Lakebase** (managed Postgres).
- **Agent Bricks** for no-code agents.

**Local → production**
- `adk web`, with sessions in a local SQLite file or in memory, becomes Agent Engine or Cloud Run with a managed session service, behind sign-in (IAP).
- Action tools that run directly become action tools behind a human approval step.
- Session and memory back ends change through configuration alone (SQLite → Cloud SQL or Agent Engine, in-memory → Memory Bank), with no change to the agent.
- An email typed into a form becomes a verified sign-in.

**Keep in mind**
- The model chooses the path; code owns the facts and the rules.
- The Runner executes; the root agent orchestrates.
- Docstrings are part of the prompt, so write them clearly.
- Nothing reaches long-term memory unless code saves it.

---

## 15. Agent interoperability: MCP and A2A

Standard ways for an agent to use tools, and for agents to work with other agents, across teams and vendors.

**Types and techniques**
- **MCP (Model Context Protocol):** an open protocol for exposing **tools, data (resources) and prompts** to any agent through an MCP server. Write the integration once, and any MCP-capable agent can use it.
  - **The server:** plain business functions, with no model code, registered as tools. The server publishes each tool's name, docstring and input schema; the docstring is the description the calling model reads.
  - **Transports:** *stdio* (the server is a local child process) or *streamable HTTP* (the server is a web service at a URL).
  - **The client:** the agent connects at run time and discovers the tools. Its code never imports the business functions, so the server's owner can change them without redeploying the agent.
  - **Tools return evidence:** the server computes facts such as "can fulfil: yes" in code, rather than leaving the model to infer them.
- **A2A (Agent2Agent):** an open protocol for one agent to **delegate a whole task** to another agent, possibly built on another framework or by another team.
  - **Agent Card:** a public description at `/.well-known/agent-card.json`: name, description, endpoint, capabilities and skills. A caller decides whether to delegate from the card alone.
  - **Opacity:** the caller sees the card and the result, never the remote agent's instruction or code. The card that ADK generates does list each tool's name and description as a skill, so write your own card when those are internal.
  - **Independent failure boundary:** the remote agent has its own lifecycle. When it's down, the calling agent still runs, so it must say the specialist is unavailable and return what it has, never fill in the specialist's facts.
  - **Not every turn delegates:** the calling agent answers general questions itself, and delegates only the work the specialist owns.
  - **Task lifecycle** *(beyond the course)*: submitted → working → input-required → completed or failed, with streamed updates.
- **MCP vs A2A:** MCP is agent → protocol → *capability*. A2A is agent → protocol → *independent agent*, with its own reasoning and tools.
- **Three ways to give an agent a capability:**
  - a **function tool:** your own code, in the same process, fastest;
  - an **MCP tool:** shared and standard, maintained by the system's owner;
  - a **remote agent (A2A):** delegates a whole task, with its own reasoning and tools. Each hop adds a model call, latency and a failure point, so a fixed lookup stays a tool.
- **Correlation across hops:** one correlation ID travels from the calling agent through the remote agent to the tool, so a bad answer can be traced end to end.
- **Identity across boundaries** *(beyond the course)*: pass the **user's** identity (not a shared super-account) to every server and agent; each one authorizes on its own. Keep an allowlist of which servers and agents may be used.
- **Risks** *(beyond the course)*: *tool poisoning* (instructions hidden in a tool description), over-broad MCP servers, injection through tool results. Pin versions and review servers like any dependency.

**GCP tools**
- **ADK MCP client:** `McpToolset` with `StreamableHTTPConnectionParams(url=...)`, or stdio parameters. `tool_filter` limits which tools the agent sees. `header_provider` adds headers to each request, such as an auth token or a correlation ID.
- **ADK A2A, server side:** `to_a2a(agent)` turns an ADK agent into a web app, served with uvicorn, that publishes its Agent Card. Install with `google-adk[a2a]`.
- **ADK A2A, client side:** `RemoteA2aAgent(name, agent_card=<card URL>, description=...)`, added as a sub-agent or wrapped in `AgentTool`. It takes `timeout` (600 seconds by default), `auth_scheme` and `a2a_request_meta_provider` for request metadata.
- **MCP Toolbox for Databases** (open source, from Google): MCP tools for BigQuery, AlloyDB, Cloud SQL, Spanner and more.
- **Agent Engine / Cloud Run:** host remote agents and MCP servers behind authentication.

**Key choices**
- **Function tool, MCP or A2A:** a local deterministic operation is a function tool; a shared, standard capability is MCP; a goal that needs its own reasoning, owner or release cycle is A2A; a conventional integration is plain REST.
- **Sub-agent or `AgentTool`:** a sub-agent takes over the conversation. With `AgentTool`, the calling agent gets the result back, or the failure text when the remote is down (ADK returns its error message as the tool result), so it can still answer.
- Which tools each agent may see, which agents may call which, and how the user's identity flows.
- Versioning and contract tests for every remote agent and server.

**Open source**
- The **MCP** Python SDK, with **FastMCP** for writing servers; the **A2A** SDK (Python, TypeScript).
- MCP support in **LangGraph**, **CrewAI** and the **OpenAI Agents SDK**.

**Databricks**
- **Managed MCP servers** for Unity Catalog functions, Genie and Vector Search; custom MCP servers on **Databricks Apps**.
- The **Agent Bricks Supervisor Agent** can use MCP servers.

**Local → production**

| Local | Production |
|---|---|
| Servers on `127.0.0.1` with fixed ports, no sign-in | Cloud Run or Agent Engine behind IAM; callers send an ID token |
| URLs and card URLs written in the code | From configuration, checked against an allowlist |
| The generated Agent Card, advertising `localhost` | A reviewed card with the public URL and only the skills callers need |
| Default timeouts (a remote agent call waits up to 600 s) | A timeout from the latency budget, with "unavailable" as a normal result |
| Logs on each side | One correlation ID and one trace across every hop |
| Local stdio servers | Remote MCP servers, pinned and reviewed |

**Keep in mind**
- A tool description is part of the prompt: an untrusted MCP server can inject instructions.
- A remote agent being down is normal. Stop it and test what the user sees.
- In ADK, an unreachable remote agent shows up as an event carrying an error message, not an exception, so nothing crashes and the failure is easy to miss.
- Every boundary authorizes on its own; never pass a shared admin credential through a chain of agents.

---

## 16. Text-to-SQL

Answering counts, totals and rankings from tables: a model writes SQL, and code checks it before it runs.

**Types and techniques**
- **When to use it:** aggregations and rankings ("top 5 stores", "highest rate"). Vector RAG is the wrong tool for numbers across many rows.
- **Maturity steps:** naive → with metadata → semantic layer → verified queries → validate and repair.
- **Schema context:** give the model the tables, columns, descriptions and real example values. Real values stop mistakes like `'Rash'` when the data says `'rash'`.
- **Knowledge catalog:** what data exists: tables, columns, synonyms ("locations" = stores), join hints.
- **Semantic catalog / semantic layer (governed metrics):** one approved formula per business metric (e.g. "net sales"), with its grain and synonyms.
- **Hybrid metadata RAG:** search the catalog descriptions, not the data rows, to pick the relevant tables and metrics. Needed only when the schema doesn't fit in the prompt.
- **Verified (golden) queries:** reviewed SQL for known questions; the model only fills in parameters.
- **SQL validation in code:** SELECT only, one statement, blocked keywords, allowed objects only.
- **Dry run + cost gate:** BigQuery compiles the query without running it, at no cost. Reject on an error or too many bytes, and check which tables it really reads.
- **Bounded repair:** feed the error back to the model, for a fixed number of tries.
- **Controlled execution:** a byte cap and a row cap; show the rows and the SQL.

**GCP tools**
- **BigQuery:** dry run, `maximum_bytes_billed`, curated and **authorized views**, row-level security, INFORMATION_SCHEMA metadata.
- **Knowledge Catalog** (formerly Dataplex Universal Catalog): a business glossary attached to columns.
- **BigQuery data agents / Conversational Analytics API:** managed natural-language-to-SQL, with glossary terms and verified queries.
- **Looker semantic layer (LookML):** governed metrics.

**Key choices**
- Curated views or full tables. Views give a smaller, safer surface.
- The whole schema in the prompt, or a catalog search.
- Which questions get verified queries.
- Show the rows word for word, or let a model narrate them (narration can reword numbers).
- A read-only identity limited to the views.

**Open source**
- **sqlglot:** parses and validates SQL properly, instead of regex.
- **Vanna**, **WrenAI**, the LangChain SQL agent.
- Semantic layers: **dbt MetricFlow**, **Cube**.

**Databricks**
- **Genie** (Genie spaces / agents): natural language to SQL over Unity Catalog.
- **Metric views:** governed metrics.
- **Trusted assets:** verified example queries and SQL functions.
- Unity Catalog comments and tags as metadata.

**Local → production**
- A developer login plus an allowlist in code becomes a read-only service account on authorized views, with row-level security and a managed glossary or semantic layer.

**Keep in mind**
- Code decides whether SQL runs. The model is never trusted to police itself.
- Never let the model invent business meaning: govern the metrics.

---

## 17. Knowledge graphs and Text-to-Cypher

Storing facts as nodes and relationships, and answering questions that follow connections. A model writes the graph query, and code checks it before it runs.

**Types and techniques**
- **Knowledge graph (the instance graph):** facts stored as nodes (a project, an employee, a skill) joined by typed relationships (`WORKS_ON`, `HAS_SKILL`, `REQUIRES`), each with properties. Suited to questions that follow connections across several hops, which take many joins in SQL.
- **Property graph vs RDF:**
  - *property graph:* nodes and relationships with properties; queried with Cypher (Neo4j) or GQL (the ISO standard);
  - *RDF:* subject–predicate–object triples; queried with SPARQL; often modeled with OWL ontologies.
- **Ontology (the meaning layer):** the model of the business, kept separate from the facts:
  - **object types** with descriptions and properties;
  - **relationship types** and what each one means;
  - **hierarchy** ("a critical risk is a kind of risk");
  - **semantic rules:** business definitions written as relationships. Example: a *skill gap* is a project that REQUIRES a skill no employee who WORKS_ON it HAS.
- **Schema vs semantic layer vs ontology:**
  - a schema says what data exists;
  - a semantic layer defines metrics (one formula per KPI);
  - an ontology defines concepts, how they may connect, and rules over those connections.
- **Ontology retrieval, in two stages:**
  1. **Semantic discovery:** embed the ontology's elements (objects, relationships, rules, never the data rows); the top-K by cosine become entry points.
  2. **Symbolic expansion:** from the entry points, follow rules, relationships and hierarchy to a connected subgraph. Keep it bounded: a cap on hops or size.
- **Why expansion matters:** embeddings find what *sounds* relevant; the ontology adds what is *required* to make sense of it. For "skill gaps", the search finds Project and Skill, and the rule adds Employee. Without it the model gets disconnected pieces and writes a wrong query.
- **Text-to-Cypher / Text-to-GQL:** the model receives the question plus **only the relevant subgraph** (never the whole ontology) and writes a read-only graph query. The database returns the facts, and the answer is grounded on them.
- **Verified graph queries:** hand-written queries for known questions (e.g. a reviewed skill-gap query), the graph version of verified SQL.
- **GraphRAG:** combines text retrieval with graph traversal. Entities and relationships are extracted from documents into a graph, and the answer uses both the passages and the connections.
- **Graph query safety:** the generated query is untrusted input. Use:
  - a read-only transaction and a read-only database user;
  - real parsing or a compile-only check (Neo4j `EXPLAIN`, which works like a dry run), not keyword lists;
  - no procedure calls;
  - timeouts, plus limits on rows and path length;
  - authorization on what each user may see.

**GCP tools**
- **Spanner Graph:** Google's managed graph database inside Spanner. It is queried with GQL (and SQL), with vector and full-text search in the same database.
- **Neo4j AuraDB** on Google Cloud (Marketplace): managed Neo4j, queried with Cypher.
- **Vertex AI embeddings:** embed the ontology's elements for the discovery stage.
- **Gemini:** writes the Cypher or GQL, and explains the facts.
- **Knowledge Catalog business glossary:** the governed vocabulary the ontology's terms can align with.

**Key choices**
- Graph or tables: a graph when questions follow multi-hop relationships; SQL when they aggregate over tables. Many systems use both.
- Property graph (Cypher / GQL) or RDF (SPARQL).
- Who owns the ontology, and how changes to it are versioned and reviewed.
- How far expansion may go: number of hops, size of the subgraph.
- The whole ontology in the prompt (when it is small) or a retrieved subgraph (when it is large).
- Show the graph facts word for word, or let a model explain them.

**Open source**
- Graph databases: **Neo4j** (Community), **Memgraph**, **Apache AGE** (a graph on Postgres), **JanusGraph**.
- RDF and ontologies: **Apache Jena**, **RDFLib**, **Protégé** (an OWL ontology editor).
- Graph RAG libraries: **neo4j-graphrag**, **LangChain** `GraphCypherQAChain`, **LlamaIndex** `PropertyGraphIndex`, **Microsoft GraphRAG**.

**Databricks**
- No managed graph database. The options are:
  - **GraphFrames** for graph analytics on Spark;
  - the **Neo4j Spark connector** to read and write an external graph;
  - relationships kept as Delta tables and queried with SQL (Genie).

**Local → production**
- The lab set-up:
  - Neo4j in Docker, with its password in an env file;
  - the graph wiped and reloaded on each run;
  - the ontology index in a local JSON file, with cosine computed in Python;
  - a keyword blocklist as the only query check.
- Production replaces it with:
  - a managed graph (Spanner Graph or AuraDB), with secrets in Secret Manager;
  - incremental loads (MERGE);
  - a managed vector index for the ontology;
  - a read-only role, parsed or compile-checked queries, timeouts;
  - a versioned ontology.

**Keep in mind**
- Embeddings find the entry points; the ontology supplies the meaning. Vector search over schema descriptions alone can return disconnected pieces.
- Expansion fixes incomplete retrieval, not an ontology that is wrong or incomplete.
- Keep expansion bounded, or the "relevant" subgraph grows into the whole ontology.
- A keyword blocklist is not a safety control.

---

## 18. Orchestration

How the system decides which capability handles a request, and how agents work together.

**Types and techniques**
- **Intent routing:** general conversation (no tool), knowledge (RAG) or analytics (SQL). The orchestrator picks a capability; each tool owns its own retrieval.
- **Ask-back:** ask when a required detail (country, date) is missing, instead of guessing.
- **Multi-tool turns:** one question can need several tools (e.g. "then vs now" → a historical search plus a current search).
- **Transfer vs agent-as-tool:** a transfer (`sub_agents`) hands the conversation over to another agent. An `AgentTool` calls a specialist like a function, and the root agent stays the only voice to the user.
- **Workflow agents:** run steps in a fixed order, with no model deciding (ADK Sequential, Parallel and Loop agents).
- **Model-driven vs deterministic:** let a model choose only where judgment is needed; use fixed pipelines everywhere else.
- **Agentic / corrective retrieval:** retrieve → assess → rewrite or retry → answer or refuse. More judgment, but more latency and cost.
- **Human in the loop:** risky cases (e.g. a question about one patient) go to a person. A classifier run by code decides, and it fails closed: "unsure" also goes to a person.
- **Supervisor pattern:** a supervisor agent delegates to specialist agents.
- **Semantic orchestration:** the middle ground between a fixed workflow and an unrestricted agent, for work whose next step can't be known in advance. "Gemini proposes. Software disposes." The loop is: objective → evidence → one structured decision → schema check → policy gate → execute one action → normalize the result → re-evaluate.
- **Agent-led vs code-led:** in an agent-led design, an `LlmAgent` picks tools from its instruction and callbacks guard each step. In a code-led design, your code runs the loop and Gemini returns one decision per step. Code-led suits multi-step investigations where every decision must be recorded.
- **Structured next-action decision:** one validated JSON decision per step: an action from an allowlist, the reason, the evidence used, the expected information gain and a confidence. An enum means an invented action fails validation.
- **Policy gate (deterministic plane):** code decides whether a proposal may run: allowlist, authorization, budgets, repetition, deadlines and the read/write boundary. A rejected proposal is recorded, and the model can re-plan within a limit.
- **Evidence register:** evidence objects instead of raw text in a growing prompt. Each has an ID, source action, source system, observed time, source time, status, freshness and correlation ID. Failed calls are evidence too.
- **Freshness policy:** a maximum age per evidence type, checked by code. Old evidence is marked `STALE_EVIDENCE`, never used as current truth.
- **Conflict policy:** rules based on source authority, freshness and known lag. An unresolved conflict is surfaced in the result, never settled by picking the last value seen.
- **Synthesis gate:** a coded rule for the minimum evidence before a conclusion, such as an authoritative record, a cause-specific source and no unresolved conflict. Confidence is not evidence.
- **Termination states:** every run ends explicitly: `SYNTHESIZE`, `STOP_INSUFFICIENT_EVIDENCE`, `ESCALATE`, or a policy, budget, failure or timeout termination. Partial results have their own states, such as `PROBABLE_CAUSE` and `CONFLICT_REQUIRES_REVIEW`.
- **No-progress detection:** action plus argument fingerprints, and checks for steps that add no new evidence. Re-checking on purpose is allowed; useless repetition isn't.
- **Epistemic discipline:** the result separates observed fact, inference, hypothesis and recommendation, and cites evidence IDs. A similar past incident guides the search, but doesn't prove today's cause.

**GCP tools**
- **ADK:** `LlmAgent` routing, `AgentTool`, `sub_agents`, workflow agents, callbacks.
- **Gemini structured output:** `response_schema` with a Pydantic model and an enum of actions, for next-action decisions.
- **Agent Engine:** hosts multi-agent systems.
- **Pub/Sub → ticketing system:** hand-off records for humans.

**Key choices**
- Which decisions need a model, and which are code.
- One router, or a hierarchy of agents.
- Agent-led or code-led orchestration.
- The minimum evidence for a conclusion, the maximum age per evidence type, and which source wins a conflict.
- When to escalate to a person, and failing closed.
- A cap on tool calls per turn.

**Open source**
- **LangGraph** (graphs with state), **CrewAI** (agents with roles), **AutoGen / AG2** (agents in conversation), **ADK**.

**Databricks**
- The **Agent Bricks Supervisor Agent**: orchestrates Genie agents, agent endpoints, Unity Catalog functions, MCP servers and custom agents.
- LangGraph on the Agent Framework.

**Local → production**
- Escalations written to a table become Pub/Sub messages to the ticketing system, and routing accuracy is monitored.
- Evidence held in memory becomes a persistent evidence and execution store, so a crashed run can be resumed or safely restarted.

**Keep in mind**
- Put every safety rule inside tools or callbacks, so a wrong route is unhelpful but never unsafe.
- Routing varies between runs even at temperature 0. Measure it.
- Running out of budget must end as an explicit incomplete result, never as an apparently successful answer.
- To prove there is no hidden `if/else` router, change one fact in the evidence and show that the next action changes while the policy doesn't.

---

## 19. Agent runtime: control and observability

The code around an agent that gives every request a trusted identity, hard limits, a check before every tool call, and a record of what happened. The model reasons; the runtime makes that reasoning controllable, observable and safe.

**Types and techniques**
- **Layers:**
  - **harness:** sets up and closes each request;
  - **Runner:** executes;
  - **plugins:** observe the whole app; **callbacks:** control each step;
  - **orchestrator agent:** decides;
  - **specialist agents and tools:** do the work.
- **Trusted request context:** created by code **before** the model runs, and read-only (frozen) for the whole request: correlation ID, user, role, business unit, geography, environment, time received. Identity and authority never come from the prompt or from arguments the model writes. Targets the user names (an employee ID, an application) are checked against it.
- **Correlation ID:** a unique ID per request, created by the runtime. It goes on every trace event, log line and downstream call (in a request header), so one request can be followed end to end. It differs from the session ID (a whole conversation) and the framework's invocation ID.
- **Execution policy (budgets):** fixed limits per request:
  - model calls;
  - tool calls;
  - identical calls;
  - failures;
  - elapsed time;
  - what to do with an unauthorized call: **block and trace**, never "allow and log" or "ask the model".

  Budgets reset for each request; add a per-session or per-user limit if long conversations are a cost or abuse risk.
- **Where each check runs:**
  - `before_model`: count model calls, and stop a call that is over budget;
  - `after_model`: record the result;
  - `before_tool`: budgets, repeats and authorization, blocking **before** the tool runs;
  - `after_tool`: classify the result, count failures, record it safely.
- **Repeated-call fingerprint:** tool name + normalized arguments (sorted, fixed format). Past the threshold, the call is blocked.
- **Controlled result:** a blocked call doesn't run. The model receives a structured error (`code`, `retryable: false`) and the run continues with the evidence it already has. You block the action, not the system.
- **Failure taxonomy:** four classes, each with its own behavior:
  - **dependency:** timeout, unavailable, rate-limited;
  - **permanent / input:** not found, invalid argument, malformed response;
  - **security:** authentication failed, authorization denied;
  - **harness / policy:** tool budget, repeated call, failure budget, time budget.
- **Failure behavior:**
  - **RETRY:** transient and retryable, with backoff and a small limit;
  - **STOP:** the target doesn't exist, or the budget is used up;
  - **CONTINUE:** a valid empty finding;
  - **DEGRADE:** continue with partial evidence, report what is missing, lower the confidence;
  - **DENY:** unauthorized, or a repeated call.

  Never let the model guess what is missing.
- **Plugin vs callback:**
  - a **plugin** is registered once on the App and observes every agent and every run (start, end, telemetry);
  - a **callback** is attached to an agent and controls one step.
- **Invocation registry:** makes the current request's context, policy and trace findable by callbacks and plugins. It uses a per-request context variable, so concurrent requests don't mix. It is reset at the end, and it is not memory.
- **Invocation trace:** timestamped events: proposals, decisions with reasons, failures, counts, how the run ended. It holds safe arguments and **references** to evidence, never raw personal data.
- **Two outputs:**
  - a **business result** (e.g. COMPLIANT, NON_COMPLIANT, INSUFFICIENT_EVIDENCE or ACCESS_DENIED, with the evidence and anything missing);
  - an **execution report** (correlation ID, budgets used, authorization decisions, how it ended, time taken).
- **Fail closed:** if the context or policy is missing, block. Don't run unchecked.
- **What ADK provides vs what you build:**
  - **ADK provides:** Agent, App, Runner, session service, InvocationContext, ToolContext, callbacks, plugins, events.
  - **You build:** request context, execution policy, registry, trace, execution report, correlation IDs, repeated-call detection, failure taxonomy, rules for ending a run.

**GCP tools**
- **ADK:** App, Runner, callbacks, plugins, events.
- **Vertex AI Agent Engine:** managed runtime, sessions and tracing.
- **Cloud Trace / OpenTelemetry:** the trace ID works as a correlation ID across services; **Cloud Logging** entries are linked to the trace.
- **IAP / Identity Platform:** the signed-in identity that fills the trusted context.
- **Apigee / API Gateway:** per-user quotas and rate limits in front of the agent.
- **BigQuery / Cloud Logging:** traces and execution reports for audit.

**Key choices**
- Budget values per request, and per session or user.
- What blocks and what only records (e.g. stop the model when over budget, or just flag it).
- Whether retries happen inside the tool or by the model asking again.
- What the trace may contain, and how long it is kept.
- What happens when the context is missing (fail closed).

**Open source**
- Step limits built into frameworks: LangGraph `recursion_limit`, OpenAI Agents SDK `max_turns` (plus guardrails and tracing), CrewAI `max_iter` / `max_rpm`.
- Tracing: **OpenTelemetry**, **Langfuse**, **Arize Phoenix**.
- Python `contextvars` for binding data to the current request.

**Databricks**
- **MLflow Tracing:** a span for each model and tool call, with request tags.
- **AI Gateway:** rate limits, usage tracking, guardrails, inference tables.
- Hosting on **Databricks Apps** / the Agent Framework; **Unity Catalog** permissions on tools.

**Local → production**
- **Identity:** from an env file → from the signed-in user (IAP).
- **Budgets:** from env values → versioned, reviewed configuration.
- **Trace:** printed to the console → Cloud Logging / Cloud Trace + BigQuery.
- **Missing context:** checks silently skipped → fail closed.
- **Sessions:** in memory → a managed session service.
- **Serving:** a single loop → a server with one active request per session.

**Keep in mind**
- The model reasons; the runtime establishes identity and control.
- Block before execution. Recording a call after it ran is not control.
- Grade the execution report, not only the answer: how it ended, the counts, and whether a blocked tool actually ran.

---

## 20. Long-running and action-taking agents · BEYOND THE COURSE

Agents that change things in other systems, or whose work takes minutes to days, done safely.

**Types and techniques**
- **Propose → approve → execute:** the agent prepares a structured proposal (what, which target, why, the evidence); a person or a policy approves; code carries it out.
- **Risk tiers:** low-risk, reversible actions may be approved automatically by policy; high-risk actions always need a person; some actions are never allowed.
- **Durable execution:** the state is saved after every step, so the work survives restarts and can wait hours for an approval, then resume.
- **Idempotency:** each action carries an idempotency key, so a retry never performs it twice.
- **Dry run / preview:** show the effect before doing it, where the target system supports it.
- **Verification:** after acting, read the target system back to confirm the change happened.
- **Compensation (undo):** every action has a defined reverse or compensating step, and an undo window.
- **Timeouts and escalation:** an unanswered approval expires or escalates.
- **Asynchronous experience:** the user gets a task ID and status updates instead of waiting at the screen.

**GCP tools**
- **ADK:** a confirmation step before a tool runs (human approval), and long-running function tools.
- **Workflows:** durable multi-step execution, with callbacks to wait for an approval.
- **Cloud Tasks:** retries and scheduling for single actions; **Pub/Sub** for events.
- **Firestore / Cloud SQL:** task state; **Agent Engine sessions** for the conversation.

**Key choices**
- Which actions exist at all, and the approval rule for each risk tier.
- The undo window, and who is accountable for an approved action.
- How long an approval may wait before it expires or escalates.

**Open source**
- **Temporal** (durable execution), **LangGraph** interrupts + checkpointers (pause for a person, resume), **Celery** / task queues.

**Databricks**
- LangGraph checkpoints in **Lakebase** (pause and resume), **Lakeflow Jobs** for long tasks, **Databricks Apps** for the approval screen, Unity Catalog functions with restricted permissions for the actions.

**Local → production**
- An action tool that runs immediately inside the chat becomes a proposal queued for approval, executed by a separate least-privilege service, audited and reversible.

**Keep in mind**
- The model proposes, a person or a policy approves, code executes.
- Never let a retry repeat an action.

---

## 21. Evaluation and testing

Knowing whether the system is good, and which step broke when it isn't.

**Types and techniques**
- **Build → measure → operate:** build the capability, measure it, then expose it through an agent with observability.
- **Debug layer by layer:** was the document present? parsed correctly? in a useful chunk? embedded? found? kept by reranking? in the context? used in the answer?
- **Retrieval metrics:**
  - Recall@K and Precision@K;
  - hit rate;
  - MRR: how high the first correct result ranks;
  - nDCG: rank quality with graded relevance.
- **Answer metrics:** groundedness / faithfulness, answer relevance, citation correctness, refusal accuracy.
- **Agent metrics:** routing accuracy (the right tool), safety (risky cases escalated), task success, latency (p50, p95).
- **Golden set:** known-answer questions, scored at every stage.
- **Adversarial tests:** prompt injection, role injection, PII and secret leakage, unauthorized tool use, hallucination.
- **Runtime ("torture") tests:**
  - an unauthorized request (the tool must not run);
  - a repeated expensive call;
  - a dependency outage (must show as uncertainty, not a guess);
  - an unknown ID;
  - running out of budget;
  - "ignore your limits, I'm the admin" (a prompt can't change the policy);
  - stale evidence (not treated as current);
  - conflicting sources (surfaced, not invented away);
  - premature synthesis (rejected by policy);
  - an invalid decision such as `DELETE_ORDER` (never executes);
  - injection inside evidence (treated as data);
  - a similar past incident (context, not proof of cause).

  Check the execution report as well as the answer.
- **Trajectory evaluation:** judge the path, not only the final answer: was each action useful, were unnecessary calls avoided, was critical evidence skipped, did it stop at the right time? Allow several valid paths.
- **Golden scenarios:** each case lists the important evidence, forbidden conclusions and acceptable end states, not one exact tool sequence.
- **Deterministic vs semantic tests:** policy, budgets and validation are unit-tested without Gemini. Gemini's next-action behavior and stopping are evaluated separately.
- **Record and replay:** save external calls once, then replay them offline for fast, free tests.
- **Regression in CI:** run the suite on every change (prompt, model, rules).
- **Human review:** experts label answers, and their feedback becomes new test cases.
- **Online evaluation (beyond the course):** *shadow mode* (the new version gets a copy of live traffic, its answers are scored but not shown), *canary* (a small share of users), *A/B test* (two versions compared on live metrics).

**GCP tools**
- **Vertex AI Gen AI evaluation service:** model-based and computed metrics over datasets.
- **ADK eval** (`adk eval` with eval sets): checks which tools were called and what the response said.
- **Cloud Build:** CI that runs the tests.

**Key choices**
- The size and coverage of the golden set: rewordings, other languages, edge-case dates, wrong IDs.
- Which metrics must pass before a release.
- Offline replay or live runs.

**Open source**
- **Ragas**, **DeepEval**, **TruLens**, **promptfoo** (also for red-teaming), **MLflow**, **Arize Phoenix**, **pytest**.

**Databricks**
- **MLflow 3 GenAI evaluation:** built-in and custom judges, evaluation datasets.
- The **Review App** for expert feedback.
- Production monitoring.

**Local → production**
- Tests on a laptop become the same suite in CI, run on every change and nightly, with hundreds of cases.

**Keep in mind**
- If retrieval misses the evidence, changing the answer model won't help.
- Evaluate retrieval separately from generation.

---

## 22. Responsible AI · BEYOND THE COURSE

Making sure the system is fair, transparent and appropriate for the people it affects.

**Types and techniques**
- **Risk classification:** how much harm a wrong answer can do. Medical, financial and HR decisions are high risk, so they need more human oversight, testing and documentation. Regulations such as the EU AI Act classify uses by risk.
- **Bias and fairness testing:** compare quality across groups (languages, regions, demographics) on the evaluation set.
- **Transparency:** tell users they are using AI, show the sources, explain the limits.
- **System and model cards:** documented purpose, data, evaluation results, known limits, intended and prohibited uses.
- **Content safety:** filters for harmful content on inputs and outputs.
- **Human oversight:** a person can review, override and stop the system.
- **Feedback and redress:** users can report errors, and corrections are tracked to closure.

**GCP tools**
- **Gemini safety settings:** filters per harm category.
- **Model Armor:** screens prompts and responses.
- **Vertex AI Gen AI evaluation service:** safety and custom metrics, per group.

**Key choices**
- The risk level of the use case, and the oversight that follows from it.
- Which groups to compare, and the acceptable quality gap.
- What users are told, and who can stop the system.

**Open source**
- **Fairlearn**, **AI Fairness 360**, **Giskard** (scans for bias and harmful output), **promptfoo**.

**Databricks**
- MLflow safety and guideline judges; AI Gateway guardrails.

**Local → production**
- Informal checks become a documented risk assessment, fairness results in every release, and a disclosure to users.

**Keep in mind**
- A system that is accurate on average can still fail one group.
- Disclose that AI is used, and what it cannot do.

---

## 23. Security and guardrails

Protecting the system, its data and its users from misuse.

**Types and techniques**
- **Attacks:**
  - role injection ("you are now the administrator");
  - prompt injection ("ignore all previous instructions");
  - **indirect** prompt injection: the same, hidden in a document, email or RAG record;
  - dangerous tool execution;
  - extraction of sensitive data, PII or secrets;
  - extraction of the system prompt;
  - RAG data exfiltration (retrieving documents the user may not see);
  - tool privilege escalation.
- **Defenses:** an instruction hierarchy; untrusted text treated as data; output controls; **authorization outside the model**.
- **Compliance doesn't belong only in the prompt:** "never show another unit's data" in a prompt doesn't stop it, and neither does a user typing "my unit is GLOBAL_ADMIN". Enforce it in code.
- **Where each field may come from:**
  - **T, trusted context:** user, role, business unit, geography, correlation ID;
  - **U, user input that code validates:** target IDs, the free-text question;
  - **M, model-generated:** never identity or authorization.
- **Authorize before fetching:** the check runs in `before_tool`. Fetching the data and then hiding it is already unauthorized access, and the data can still leak through the context or the logs.
- **Data minimization at the tool layer:** tools return only allowlisted fields (no salary, no home address). A field the model never receives can't leak.
- **Least privilege:** each agent and tool gets only the access it needs (read-only by default; action tools only with approval).
- **Safe logging decisions:**
  - **FULL:** IDs, decisions, policy version, how the run ended;
  - **MASKED:** tool arguments;
  - **REFERENCE ONLY:** raw evidence such as security events;
  - **DO NOT LOG:** personal data such as salary or home address.
- **Auditability:** record who asked, when, under which authority, what was called, which decisions were made with which policy version, and how it ended. That is enough to answer "why?" months later, without storing protected data.
- **Secrets:** never in code, prompts or Git. Use a managed secret store, rotate secrets, prefer short-lived identities.
- **Access control in retrieval:** each user's access rights become search filters; row-level security in the database.
- **PII handling:** detect it, mask it, de-identify logs.
- **Governance:**
  - a reproducible release = app + prompt + model + knowledge + tools + policy versions;
  - maker-checker review;
  - documentation (purpose, owner, allowed data, prohibited actions, escalation path);
  - a map of the data flow for compliance.
- **When not to use AI:** facts that must be exact, or that carry legal weight, come from databases, rules and APIs.

**GCP tools**
- **Model Armor:** screens prompts, responses and documents for injection, jailbreaks, malicious URLs and sensitive data.
- **Sensitive Data Protection (DLP):** finds and de-identifies personal data.
- Identity and access: **IAM** with service accounts, **IAP** (sign-in), **Secret Manager**, **VPC Service Controls**.
- **Cloud Audit Logs**.
- BigQuery **authorized views** and **row-level security**.

**Key choices**
- What code blocks, and what a service screens.
- What may be logged.
- The escalation path for risky requests.

**Open source**
- Guardrails: **NeMo Guardrails**, **Guardrails AI**, **LLM Guard**.
- **Microsoft Presidio** (PII).
- Red-teaming: **garak**, **promptfoo**.

**Databricks**
- **Unity Catalog** grants, row filters and column masks.
- Service principals; secret scopes.
- **AI Gateway** guardrails (PII, safety) and usage logging.

**Local → production**
- A personal login, keys in `.env` and everyone seeing every document become: service accounts, Secret Manager, sign-in, access rights as filters, VPC Service Controls.

**Keep in mind**
- "Do not reveal PII" in a prompt is not a control.
- The user doesn't have to write the attack: a document can carry it.

---

## 24. Platform security, isolation and residency · BEYOND THE COURSE

Protecting the platform underneath the agent: networks, encryption, tenants, and where data lives.

**Types and techniques**
- **Private networking:** services, and Google APIs, are reached over private addresses instead of the public internet.
- **Data perimeter:** a boundary around projects that blocks data from leaving even when someone holds valid credentials (protection against stolen keys).
- **Encryption:** at rest with Google-managed keys or **customer-managed keys** (which you control and can revoke); in transit with TLS.
- **Edge protection:** a web application firewall and DDoS protection in front of public endpoints.
- **Identity:** SSO and MFA for people; workload identities (no keys) for services.
- **Multi-tenancy models:**
  - **silo:** a separate project, index and keys per tenant (strongest isolation, highest cost);
  - **pool:** shared resources with a tenant ID on every row, row-level security and tenant filters on every search;
  - **bridge:** a mix, e.g. shared compute with separate data.

  Isolation must cover indexes, prompts, caches, logs and evaluation data, not just the database.
- **Data residency:** data and processing stay in approved regions. That includes the model endpoint: a global endpoint may process data elsewhere.
- **Posture and threat detection:** continuous checks for misconfiguration and threats.

**GCP tools**
- Networking: **VPC**, **Private Service Connect**, **Private Google Access**.
- Perimeter: **VPC Service Controls**.
- Keys: **Cloud KMS** (customer-managed encryption keys).
- Edge: **Cloud Armor** + an external load balancer.
- Identity: **Cloud Identity / Workforce Identity Federation**, **Workload Identity**.
- Residency: **Organization Policy** (allowed resource locations), **Assured Workloads**.
- Detection: **Security Command Center**.

**Key choices**
- Silo or pool tenancy.
- Which data needs customer-managed keys.
- The allowed regions, and whether a global model endpoint is acceptable.
- What sits inside the perimeter.

**Open source**
- **Open Policy Agent** (policy as code), **HashiCorp Vault** (secrets), **Trivy** (scanning).

**Databricks**
- **Private Link**, customer-managed keys, IP access lists, serverless egress controls.
- The compliance security profile; separate catalogs or workspaces per tenant or region.

**Local → production**
- Public endpoints, Google-managed keys and one shared project become private networking, a perimeter, customer-managed keys where required, a defined tenancy model and region restrictions.

**Keep in mind**
- Check residency rules for every service, including the model.
- Tenant isolation has to cover caches and logs too, not only the index.

---

## 25. Operations: logs, caching, cost, scale

Running the system day to day, and knowing when something goes wrong.

**Types and techniques**
- **Structured logs:** one row per request (filters, evidence, checks, latency, model) and one per pipeline check. Tag test traffic separately from real use.
- **Correlation across logs:** every row of one request carries the same correlation ID (see the agent runtime concept, §19), so a request can be followed across agents, tools and downstream systems.
- **Tracing:** each model call and tool call recorded as a span (OpenTelemetry).
- **Metrics and alerts:** latency (p50, p95), block rate, escalation rate, 429 rate, freshness.
- **Caching (four kinds):**
  - embedding cache;
  - retrieval cache;
  - prompt/context cache;
  - answer cache (a *semantic* answer cache matches by meaning; see Model gateway).

  The cache key must include the corpus version, the user's access rights and freshness. A fast stale answer is still wrong.
- **Retries with backoff:** for 429 (quota) and 503 (busy) errors.
- **Cost:** count cost per successful task (model calls, retries, retrieval, validation, human escalation). Use cheaper models where measured good enough; cap the bytes queries can scan.
- **ROI:** useful work automated − human rework − inference and tool cost − failures − risk.
- **Scale:**
  - ANN indexes;
  - batch processing;
  - reserved model capacity;
  - summarized catalogs in agent instructions;
  - larger evaluation sets.
- **Backpressure:** bursts are absorbed, not passed on: queues, per-dependency rate limits, priorities, deadlines and load shedding. A model can't reason its way past a warehouse API limited to 100 requests a minute.
- **Run versions:** record `model_id`, `prompt_version`, `decision_schema_version`, `policy_version` and `tool_contract_version` with every run, so behavior can be traced and rolled back.
- **Model failure:** plan for timeouts, quota exhaustion, invalid structured output, safety refusals and unavailability: bounded retry, a fallback model, deterministic degradation, queueing or human escalation.
- **Durable recovery:** know what happens if the process dies at step 4: execution ID, saved evidence and decisions, resume or restart, and no duplicate calls.
- **Runbook:** written steps for Gemini or a key API being down, spikes in rejections, repeats, latency or cost, wrong behavior, a bad prompt or policy release, and rollback.

**GCP tools**
- Monitoring: **Cloud Logging**, **Cloud Monitoring** (alerts), **Cloud Trace** (ADK traces), **BigQuery** log tables, **Looker Studio** dashboards.
- Capacity and caching: **Provisioned Throughput**, **Gemini context caching**, **Memorystore** (Redis).
- Budgets and billing alerts.

**Key choices**
- What one log row contains, and how long logs are kept.
- What is cached, and how the cache is invalidated.
- The latency target, agreed with the customer.

**Open source**
- **OpenTelemetry**, **Langfuse**, **Arize Phoenix**, **Prometheus / Grafana**, **Redis**.

**Databricks**
- **MLflow Tracing**, inference tables.
- **System tables** (billing and usage); AI/BI dashboards.
- Provisioned-throughput endpoints.

**Local → production**
- A health report built from log tables becomes dashboards and alerts, with reserved capacity and streamed responses.

**Keep in mind**
- Govern on more than accuracy: task success, cost per task, escalations, latency, incidents.

---

## 26. Reliability: SLOs, failover and incidents · BEYOND THE COURSE

Keeping the system available and predictable, and recovering when it isn't.

**Types and techniques**
- **SLIs and SLOs:** measured indicators (availability, p95 latency, the share of requests answered successfully) and the targets for them. An **error budget** is how much failure is allowed before changes are frozen.
- **Capacity:** quotas, reserved model capacity, autoscaling, load tests.
- **Graceful degradation:** when a dependency fails, give a reduced but safe service instead of failing or guessing, e.g. search results without a generated summary, a "service busy" message, or read-only mode.
- **Timeouts and circuit breakers:** bound every call; stop calling a failing dependency for a while.
- **Model fallback and multi-region deployment** (see Model gateway).
- **Backups and recovery:** RPO (how much data you can lose) and RTO (how fast you recover); versioned indexes, so a bad load can be rolled back.
- **Incident response:** on-call, runbooks, status updates, and blameless postmortems that each add a test.

**GCP tools**
- **Cloud Monitoring:** SLO monitoring and burn-rate alerts.
- **Cloud Run** in several regions behind a **global load balancer**.
- **BigQuery:** multi-region datasets, time travel, table snapshots.
- **Cloud Storage:** dual- or multi-region buckets.
- **Provisioned Throughput** for model capacity.

**Key choices**
- SLO targets, agreed with the customer.
- What the degraded mode is, decided in advance.
- RPO and RTO; single region or several.

**Open source**
- **Prometheus** + Alertmanager, **Grafana** SLO dashboards.
- Resilience libraries: **tenacity** (retries), **pybreaker** (circuit breakers).
- Load testing: **k6**, **Locust**.

**Databricks**
- Serving-endpoint autoscaling and provisioned throughput; AI Gateway fallbacks.
- Delta time travel and deep clone for recovery; SQL alerts.

**Local → production**
- One region and no targets become agreed SLOs, error budgets, a defined degraded mode, and tested failover and restores.

**Keep in mind**
- Decide the degraded mode before the outage.
- A backup you have never restored is not a backup.

---

## 27. Environments and delivery · BEYOND THE COURSE

Moving changes from a developer's laptop to production safely and repeatably.

**Types and techniques**
- **Separate environments:** dev, test, staging, production, each with its own project, data and credentials.
- **Everything versioned:** code, prompts, policies, evaluation sets, infrastructure, index builds.
- **Infrastructure as code:** every resource defined in code and applied the same way in each environment.
- **Build once, promote the same artifact:** the image tested in staging is the one deployed to production.
- **Supply-chain security:** pinned dependencies, vulnerability scanning, signed images, and only signed images may run.
- **Test data:** synthetic or masked data outside production.
- **Promotion gates:** tests and the evaluation release gate must pass; production needs an approval.
- **Progressive rollout and rollback:** canary, traffic split, instant rollback of code, prompt and index together.
- **Configuration per environment:** models, thresholds and endpoints in configuration; secrets per environment.

**GCP tools**
- **Terraform / Infrastructure Manager** (managed Terraform).
- **Cloud Build**, **Artifact Registry** + Artifact Analysis (scanning), **Binary Authorization** (signed images only), **Cloud Deploy** (promotion and canary).
- **Developer Connect** for Git repositories; **Secret Manager**; a separate project per environment.

**Key choices**
- How many environments, and what data each may use.
- Who approves promotion to production.
- How index and prompt versions roll back together with the code.

**Open source**
- **GitHub Actions / GitLab CI**, **Terraform / OpenTofu**, **Argo CD**, **Sigstore cosign**, **Trivy**.

**Databricks**
- **Databricks Asset Bundles**, Git folders, separate workspaces or catalogs per environment, the Terraform provider, Unity Catalog model aliases (e.g. champion / challenger).

**Local → production**
- One project and deploys from a laptop become separate projects, CI/CD from Git, signed artifacts and gated promotion.

**Keep in mind**
- A prompt or index change is a release, and goes through the same gates as code.

---

## 28. FDE practice

How a forward-deployed engineer approaches the design.

**Do not begin with the model**
Begin with the enterprise problem: the users, the data, the authority boundaries, the failure modes and the operational requirements. Then decide where AI belongs.

**Discovery gate**
Ask the questions whose answers change the architecture: source of truth, authority and versions, jurisdiction, freshness SLA, access, citations, tables and figures, scanned content, abstention. Mark the **blockers**: the answers you need before you finalize the production design.

For an agent that touches sensitive systems, also ask:
- who may use it, and across which business units or countries;
- which systems hold personal data;
- which actions it may take;
- what must be audited, and how long records are kept;
- what happens when a source system is down.

Each question must change a design decision; if the answer wouldn't change anything, drop it.

**Path to autonomy**
Start read-only, with a person starting each task. Then add, one measured step at a time: automatic start → prioritizing and queueing → grouping systemic incidents → delivering results without being asked → shadow mode → proposals with human approval → automatic only for narrow, reversible, low-risk cases. High-impact actions always keep a person.

**Maturity levels**
- **Level 1, demo:** Gemini calls tools and produces an answer. Not enough.
- **Level 2, functional:** structured next actions, several tools, adaptive execution.
- **Level 3, enterprise:** adds deterministic policy, budgets, evidence provenance, failure handling and observability. The normal target.
- **Level 4, production-grade:** adds security boundaries, reliability, evaluation, economics, deployment, a runbook, versioning and an owner.

**Production readiness review**
Before calling a design production-ready, answer with evidence: source of truth, which tools can be retried, what happens when Gemini or a dependency is down, how stale and conflicting evidence are handled, who may see sensitive evidence, how secrets are managed, what is logged, how a bad prompt or policy is rolled back, how a model upgrade is evaluated, the maximum cost, what prevents loops and premature conclusions, what happens after a restart, how duplicate writes are prevented, how a bad result is debugged, and how business impact is measured.

**Customer constraints**
A strong design adapts without collapsing when a constraint arrives late: an API costs money per call, payment data can't enter Gemini, a feed is delayed by 20 minutes, customer names can't appear in traces, or the model must be replaceable.

**Architecture decision table**
Before coding, decide and justify:
- session storage;
- where authorization comes from;
- cross-unit access;
- what is logged;
- how repeated calls are handled;
- the failure taxonomy;
- where telemetry lives;
- who enforces policy;
- how much autonomy the agent gets.

**Defend every decision**
"I selected ___ because the workflow requires ___. The constraints are ___. We will evaluate it with ___. I would change it if ___." Keep a decision log.

**Design principles**
1. The model chooses the path, never the facts.
2. The register is the source of truth: metadata never comes from parsed text or from the model.
3. Authority over relevance.
4. Check every AI output against something that is not AI.
5. The user sees only checked text, word for word.
6. Fail closed on safety. When unsure, hand over to a person.
7. Structure before size: tables whole, generated text labelled, filler never searched.
8. Measure, then decide.
9. Cheap, repeatable runs: caches, pinned versions, recorded responses for tests.
10. No business facts hard-coded: rules in config and policy files.
11. Identity and limits are set by the runtime before the model runs; the model can never raise them.

**Start from the failure mode, not the technology**
| Failure | First tactic |
|---|---|
| exact ID or clause missed | lexical / hybrid search |
| paraphrase missed | semantic search |
| right paragraph, missing context | parent-child / neighbors |
| repetitive documents, wrong section | contextual chunks + metadata |
| broad question misses an aspect | multi-query |
| multi-part question | decomposition |
| too many mediocre hits | reranking |
| scores not comparable | RRF |
| question types vary | router |
| aggregation or numbers | text-to-SQL |
| relationship-heavy question | graph-assisted retrieval |
| context too large | compression |
| repeated expensive context | caching |
| no traceability | provenance / citation-aware indexing |
| unsupported answers | refusal gate |
| quality unclear | golden-set evaluation |

**Anti-patterns**
- "We have a vector DB, so we have RAG."
- Raising top-K until the answer appears.
- One chunk size for every source.
- Letting the model invent business meaning.
- Vector RAG for aggregations.
- Treating similarity as confidence.
- Adding reranking without measuring retrieval.
- Citing a document without mapping claims to evidence.
- One giant prompt containing all data.
- Hard-coded `if/else` presented as semantic orchestration.
- Every case calling every tool.
- Treating confidence as evidence, or historical similarity as current cause.
- Retrying everything, or logging everything.
- Treating the final answer as the audit trail.
- Declaring production readiness because one demo succeeded.

---

## 29. Quick map: GCP · open source · Databricks

| Concept | GCP | Open source | Databricks |
|---|---|---|---|
| Ingestion | Cloud Storage, Eventarc, Cloud Run, Pub/Sub, Workflows | Airflow, Prefect, Beam, Unstructured | Volumes, Auto Loader, Lakeflow |
| Parsing | Document AI Layout Parser, Enterprise OCR | Docling, Unstructured, Marker, Tesseract | `ai_parse_document` |
| Chunking | Layout Parser chunking, RAG Engine | LangChain / LlamaIndex splitters, Chonkie | Python in notebooks / pipelines |
| Embeddings | Vertex AI embeddings, BigQuery `AI.EMBED` | sentence-transformers, BGE, E5 | Foundation Model APIs, managed embeddings |
| Vector storage | BigQuery, Vertex AI Vector Search, AlloyDB | pgvector, FAISS, Qdrant, Weaviate, Milvus | Mosaic AI Vector Search |
| Data governance *(beyond)* | Knowledge Catalog lineage, Sensitive Data Protection, retention policies | OpenLineage, DataHub, Great Expectations | Unity Catalog lineage, Delta `VACUUM` |
| Search | BigQuery `VECTOR_SEARCH` / `SEARCH`, Vertex AI Search | Elasticsearch / OpenSearch, rank_bm25 | Vector Search hybrid |
| Reranking | Vertex AI Ranking API | bge-reranker, cross-encoders, ColBERT | Vector Search reranker |
| Context | Gemini context caching | LlamaIndex postprocessors, LLMLingua | Agent Framework code |
| Models | Gemini on Vertex AI, Model Garden | vLLM, Ollama, Gemma, Llama | Foundation Model APIs, AI Gateway |
| Model gateway *(beyond)* | Apigee, Model Garden, Vertex AI tuning, batch prediction | LiteLLM, Portkey, GPTCache, TRL / PEFT | Mosaic AI Gateway, Foundation Model Fine-tuning |
| Answer generation | Gemini structured output, grounding | Pydantic, Instructor, DSPy | structured outputs, MLflow Prompt Registry |
| Answer checks | Check Grounding, Gen AI evaluation | Guardrails AI, NeMo Guardrails, Ragas | MLflow 3 judges, AI Gateway guardrails |
| Agents | ADK, Agent Engine, Cloud Run, Memory Bank | LangGraph, CrewAI, AutoGen | Agent Framework, Databricks Apps, Lakebase |
| Agent interoperability | ADK `McpToolset`, `to_a2a` + `RemoteA2aAgent`, MCP Toolbox for Databases | MCP SDK (FastMCP), A2A SDK | Managed MCP servers, Databricks Apps |
| Text-to-SQL | BigQuery, Knowledge Catalog, data agents, Looker | sqlglot, Vanna, dbt MetricFlow, Cube | Genie, metric views, trusted assets |
| Knowledge graphs | Spanner Graph (GQL), Neo4j AuraDB on Google Cloud | Neo4j, Memgraph, Apache AGE, neo4j-graphrag, Microsoft GraphRAG | GraphFrames, Neo4j Spark connector |
| Orchestration | ADK routing, AgentTool, workflow agents, Gemini structured output | LangGraph, CrewAI | Agent Bricks Supervisor Agent |
| Agent runtime | ADK App / Runner / callbacks / plugins, Agent Engine, Cloud Trace, IAP, Apigee | LangGraph `recursion_limit`, OpenAI Agents SDK `max_turns`, OpenTelemetry, Langfuse | MLflow Tracing, AI Gateway, Databricks Apps |
| Long-running & action agents *(beyond)* | ADK tool confirmation, Workflows callbacks, Cloud Tasks | Temporal, LangGraph interrupts | Lakebase checkpoints, Lakeflow Jobs, Apps |
| Evaluation | Gen AI evaluation service, `adk eval` | Ragas, DeepEval, promptfoo, MLflow | MLflow 3 evaluation, Review App |
| Responsible AI *(beyond)* | Gemini safety settings, Model Armor, Gen AI evaluation | Fairlearn, AI Fairness 360, Giskard | MLflow safety judges, AI Gateway |
| Security | Model Armor, DLP, IAM, IAP, VPC-SC | NeMo Guardrails, Presidio, garak | Unity Catalog, AI Gateway |
| Platform security *(beyond)* | VPC-SC, Private Service Connect, Cloud KMS, Cloud Armor, Assured Workloads, SCC | Open Policy Agent, Vault, Trivy | Private Link, customer-managed keys, egress controls |
| Operations | Cloud Logging / Monitoring / Trace, Looker Studio | OpenTelemetry, Langfuse, Phoenix | MLflow Tracing, system tables |
| Reliability *(beyond)* | Cloud Monitoring SLOs, multi-region Cloud Run, BigQuery snapshots | Prometheus, Grafana, k6, tenacity | Serving autoscaling, AI Gateway fallbacks, Delta time travel |
| Environments & delivery *(beyond)* | Terraform, Cloud Build, Artifact Registry, Binary Authorization, Cloud Deploy | GitHub Actions, OpenTofu, Argo CD, cosign | Asset Bundles, Git folders, UC model aliases |
