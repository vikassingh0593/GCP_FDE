# Stage 2: Knowledge (RAG)

**Goal:** turn documents into evidence the agent can find, cite and prove.
**Skip if:** the use case has no documents. Say so.
**Go deeper:** concepts.md §1–§9 and §12–§13; arch.md flow 1 (ingestion) and branch K of flow 2.

## Build order

Build one capability, measure it, then put an agent on top. Don't start with the agent.

1. **Ingest:** originals in versioned storage, metadata from the register.
2. **Parse:** layout-aware parsing and OCR, then a quality gate. Look at the output before going further.
3. **Chunk:** decide what must survive intact, then the size.
4. **Embed:** document task type for chunks, query task type for questions.
5. **Store and index:** staging plus MERGE, filter columns, then verify that a real search finds it.
6. **Search:** hard filters first, then hybrid search.
7. **Rerank:** a generous candidate pool down to a few.
8. **Build context:** evidence cards, authority order, sufficiency check.
9. **Generate:** structured output, citations, abstention.
10. **Verify:** every AI output against something that isn't AI.

### Sensible defaults (measure, then change)

| Decision | Default |
|---|---|
| Parser | Document AI Layout Parser, version pinned; OCR for scans |
| Chunks | Heading-aware, about 512 tokens, tables whole, heading path added, no fixed overlap; neighbor expansion at answer time |
| Store | BigQuery with `VECTOR_SEARCH` beside text and metadata |
| Index | Exact search for small tables (BigQuery's vector index needs 5,000 rows); an index with stored filter columns above that |
| Search | Hybrid, fused with RRF (k ≈ 60), top 20–50 candidates |
| Rerank | Vertex AI Ranking API, down to about 5 |
| Answer | Gemini with a response schema, low temperature |

## Checks

### KN-01 · High · Metadata comes from the register
- **Look for:** status, version, country and dates loaded from the owning system.
- **Why:** metadata from a model or parsed text is a guess. A guessed status can show withdrawn guidance as current.
- **Fix:** join chunks to the register. Status changes then flip by join, with no re-embedding.

### KN-02 · High · A quality gate runs before indexing
- **Look for:** checks on page count, OCR quality, junk characters, tables intact, and faithfulness to the file's own text. Failures quarantine.
- **Why:** parsers change content. In one real build Layout Parser rewrote "25 mg OD" as "25 mg QD" in a drug table. Only a faithfulness check caught it.
- **Fix:** compare parsed text with the native text, flag differences for review, and never index a failed document silently.

### KN-03 · High · Loads are idempotent
- **Look for:** staging table plus MERGE; one document's rows replaced as a unit.
- **Why:** a retry that appends duplicates quietly distorts search and counts.
- **Fix:** make a re-run produce the same result. Test by running twice.

### KN-04 · High · "Loaded" is proved by a real search
- **Look for:** a probe query per document after the load.
- **Why:** a row in a table isn't the same as findable.
- **Fix:** run a probe through the real search path, and fail the pipeline if it misses.

### KN-05 · Medium · Parser version is pinned and results are cached
- **Look for:** a pinned processor version, and a cache keyed by file hash plus version and settings.
- **Why:** a new version can change every chunk without warning, and re-parsing wastes money.
- **Fix:** pin it, test upgrades, and key the cache on hash + version.

### KN-06 · High · The unit of evidence survives chunking
- **Look for:** tables whole with headers. Long tables split by rows with the header repeated. No chunk crosses a heading.
- **Why:** a table row without its header is meaningless, and the model will misread it.
- **Fix:** ask "what must survive intact?" per document type. Add an automated check that known tables land in one chunk.

### KN-07 · Medium · Noise and generated text are labelled
- **Look for:** templates and duplicates tagged and kept out of search; figure descriptions marked as generated.
- **Why:** boilerplate crowds out real content, and generated text must never be cited as the document's words.
- **Fix:** tag and filter. Find repeated text by comparing number-masked sentence shapes across different chunks.

### KN-08 · Medium · Chunk size was chosen by experiment
- **Look for:** results comparing sizes on real questions.
- **Why:** one size for every source is an anti-pattern, and a default is only a guess.
- **Fix:** sweep a few sizes per document type against the golden set, and record the decision.

### KN-09 · High · Embeddings use task types and one model per index
- **Look for:** document type for chunks, query type for questions, a single model per index.
- **Why:** the wrong task type quietly lowers recall, and vectors from two models can't be compared.
- **Fix:** set task types. Changing the model means re-embedding into a parallel copy and switching after testing.

### KN-10 · Medium · Embedding work is cached
- **Look for:** a cache keyed by a hash of text plus model.
- **Why:** re-embedding unchanged text wastes money. A re-run should embed nothing new.
- **Fix:** store the hash beside the vector, and skip matches.

### KN-11 · Blocker · Hard filters run before the search, with parameters
- **Look for:** status, country, date and user access applied before ranking, from trusted values, passed as query parameters.
- **Why:** these are governance controls. Filtering afterwards can return nothing, or show a document the user may not see.
- **Fix:** filter in the SQL `WHERE`, or pre-filter a subquery, with parameters. Never paste values into SQL text.

### KN-12 · High · Search type matches the question
- **Look for:** exact IDs handled by lookup or lexical search. Hybrid for general text.
- **Why:** vector search never returns empty. Asked for a document that doesn't exist, it returns something similar, and the agent presents it as the answer.
- **Fix:** route exact IDs to a lookup that can say "no such document".

### KN-13 · Medium · Index recall is measured
- **Look for:** recall against exact search once an index exists.
- **Why:** an approximate index can silently drop the right answer.
- **Fix:** compare it with exact search on the golden set.

### KN-14 · Medium · Relevance and authority are separate
- **Look for:** reranking for relevance, then code ordering by source type and status.
- **Why:** the most relevant passage may not be the one with authority.
- **Fix:** write authority rules with the customer and apply them in code.

### KN-15 · High · The system can abstain
- **Look for:** a sufficiency check before generation, using several signals, such as key-term coverage and the right country or product.
- **Why:** a similarity score isn't confidence. Without this, the model answers from whatever it was given.
- **Fix:** if the evidence isn't enough, abstain without calling the model. "I don't have this" is a correct answer.

### KN-16 · High · Answers are structured and cited
- **Look for:** JSON output with citations to numbered evidence cards whose headers are written by code.
- **Why:** code can only check what it can parse, and a header written by code can't be invented.
- **Fix:** use a response schema. Code builds the source list; the model doesn't.

### KN-17 · Blocker · Every AI output is checked by something that isn't AI
- **Look for:** citation check, number check, premise check and claim check against table cells. Fail closed. One repair try at most.
- **Why:** valid JSON isn't a correct answer. A grounding score is an estimate; exact checks are proof.
- **Fix:** add code checks after generation. If a check can't run, block rather than pass.

### KN-18 · Medium · The user sees only checked text
- **Look for:** the agent relaying the checked answer word for word, with additions written by code.
- **Why:** an agent that rewords a checked answer removes the check.
- **Fix:** use an `after_model_callback` to relay the tool's answer verbatim.

### KN-19 · Medium · Context has a budget and marks evidence as data
- **Look for:** a size cap, and evidence inside clear markers labelled as data, not instructions.
- **Why:** more context adds cost and distraction, and a document can carry an injection.
- **Fix:** cap it, order it by authority, and mark it.

### KN-20 · High · Withdrawn content leaves everywhere
- **Look for:** a way to remove a document from storage, chunks, index, facts and caches. Superseded and withdrawn are treated differently.
- **Why:** a recalled document still in a cache or index will keep being cited.
- **Fix:** keep an inventory of every copy. Superseded stays for "what applied then" questions; withdrawn leaves immediately.

### KN-21 · Medium · Model settings are measured, not assumed
- **Look for:** evidence behind thinking and temperature choices.
- **Why:** in one real build, turning thinking off to save time made two of three answers state the wrong starting dose, and they passed every check.
- **Fix:** compare settings on the golden set, and add a regression test for what you find.

### KN-22 · High · Chunks per document are counted after parsing
- **Look for:** a count of chunks per document after parsing, compared with the document's sections.
- **Why:** a parser's chunk size is a maximum, not a target. Document AI Layout Parser returns a short document as one chunk, so section search silently becomes document search and the right section never ranks.
- **Fix:** split at headings after parsing when the unit of evidence is a section, keep the heading path on every piece, and fail ingest when a long document comes back as one chunk.

### KN-23 · Medium · Each search leg is measured alone and fused
- **Look for:** hit@1, hit@5 and MRR for dense only, lexical only and hybrid, on the same questions.
- **Why:** a lexical leg over ordinary words can make hybrid worse than dense alone, because long, wordy documents win on word counts. Without each leg measured alone, nobody notices.
- **Fix:** restrict the lexical leg to exact codes and IDs, keep a leg only if fused beats it, and record the numbers.

### KN-24 · High · The ranker version is pinned, and a ranker outage has a defined fallback (scan)
- **Look for:** a ranker model with a fixed version in configuration (not `@latest`), and what search returns when the ranker call fails.
- **Why:** `@latest` can move without a code change, and the relevance threshold was measured on one version. When the ranker is down, a threshold on missing scores either lets everything through or nothing.
- **Fix:** pin the version and re-measure the threshold before changing it. On a ranker failure, keep only results verifiable without a score (exact-code matches), say the search is degraded, and never cache that result.

## Local → production

| Lab | Production |
|---|---|
| Manual upload and a script run by hand | Event per file → Cloud Run, plus a nightly reconcile sweep and alerts |
| Exact search, no per-user filters | Index with stored filter columns, user access rights as filters |
| Checks run once by hand | Same checks in the pipeline, with sampled human review |

## Defend it

- Why does retrieval have to be evaluated separately from the answer?
- Why isn't a similarity score a confidence score?
- What happens when someone asks for a document that doesn't exist?
- What stops the model from inventing a number?
- Why is a parser's chunk size not the size of your chunks?
