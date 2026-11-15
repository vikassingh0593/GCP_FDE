# Stage 3: SQL and graph data

**Goal:** answer counts, rankings and relationships from real data, with every generated query checked by code before it runs.
**Skip if:** the use case has no tables or relationships to query.
**Go deeper:** concepts.md §16–§17; arch.md flow 2, branches S and G.

## Which tool for which question

| Question | Use |
|---|---|
| Concepts and explanations | Document search (Stage 2) |
| Counts, totals, rankings across rows | Text-to-SQL |
| Connections across several hops | Graph query |

Vector RAG is the wrong tool for numbers across many rows.

## Build order

**Text-to-SQL maturity:** naive → with metadata → semantic layer → verified queries → validate and repair. Don't stop at naive.

1. Create curated views, and a read-only identity limited to them.
2. Build schema context from metadata plus real example values.
3. Write verified queries for known questions.
4. Add one approved formula per business metric.
5. Add validation in code, then a dry run with a cost cap.
6. Add bounded repair, then controlled execution with caps.

**Graph:** build the ontology first, then embed the ontology's elements (never the data rows), find entry points by meaning, expand through rules within a limit, and give the model only that subgraph.

## Checks

### DB-01 · High · Numbers come from the database
- **Look for:** aggregates computed by SQL, not by the model and not by vector search.
- **Why:** the database counts; a model estimates.
- **Fix:** route metric questions to SQL.

### DB-02 · Blocker · Code validates SQL before it runs
- **Look for:** SELECT only, one statement, allowed objects only, using a real parser such as sqlglot.
- **Why:** the model isn't trusted to police itself. Regex checks miss comments, CTEs and multiple statements.
- **Fix:** parse the SQL and check it. Reject anything outside the allowed views.

### DB-03 · Blocker · Queries run with a read-only identity on curated views
- **Look for:** a service account limited to views, not a developer login or owner account.
- **Why:** if validation ever fails, the identity is the last line of defense.
- **Fix:** use a read-only service account on authorized views. Validation and identity are two independent controls.

### DB-04 · High · Dry run, byte cap and row cap
- **Look for:** a dry run before execution, plus `maximum_bytes_billed` and a row limit. Check which base tables the query really reads.
- **Why:** one bad query can scan terabytes and cost real money.
- **Fix:** reject on error or size, and cap execution.

### DB-05 · High · Schema context has real values
- **Look for:** tables, columns, descriptions and actual example values.
- **Why:** real values stop mistakes like `'Rash'` when the data says `'rash'`, which return zero rows without any error.
- **Fix:** add sample values from metadata. Search catalog descriptions, not data rows, if the schema doesn't fit.

### DB-06 · Medium · Metrics are governed, and known questions use verified queries
- **Look for:** one formula per metric. Reviewed SQL for known questions.
- **Why:** if the model defines "net sales", two runs can give two answers.
- **Fix:** add a semantic layer and verified queries. The model fills in parameters only.

### DB-07 · Medium · Repair is bounded
- **Look for:** a fixed number of repair tries, feeding back the real error.
- **Why:** unbounded repair is a cost loop.
- **Fix:** cap it, then report that the question couldn't be answered.

### DB-08 · High · Results reach the user unchanged
- **Look for:** rows and SQL shown as returned.
- **Why:** narration can reword numbers. An answer that looks checked but was retyped by a model isn't checked.
- **Fix:** show the rows word for word, or re-check any narration against them.

### DB-09 · High · Values are parameters, not pasted text (scan)
- **Look for:** f-strings that build SQL with non-constant values.
- **Why:** pasting user or model text into SQL is SQL injection, and a filter can be bypassed.
- **Fix:** use query parameters. Upper-case constants and configuration are fine in the text.

### DB-10 · High · Row-level access comes from trusted context
- **Look for:** row-level security or filters based on the caller's verified identity.
- **Why:** a question like "show me all units" must not widen access.
- **Fix:** apply it in the database or in code from the trusted context, never from the question.

### DB-11 · Blocker · Graph queries are treated as untrusted input
- **Look for:** a read-only transaction and user, a compile-only check (Neo4j `EXPLAIN`), no procedure calls, timeouts, and limits on rows and path length.
- **Why:** a keyword blocklist isn't a safety control.
- **Fix:** use all of these together. Authorize what each user may see.

### DB-12 · Medium · Graph expansion is bounded
- **Look for:** a cap on hops or subgraph size.
- **Why:** without a cap, the "relevant" subgraph grows into the whole ontology.
- **Fix:** cap it, and give the model only the connected subgraph.

### DB-13 · Medium · The ontology has an owner and versions
- **Look for:** an owner, reviewed changes, and semantic rules written as relationships.
- **Why:** expansion fixes incomplete retrieval, not a wrong ontology.
- **Fix:** version it like code.

## Local → production

| Lab | Production |
|---|---|
| Developer login plus an allowlist in code | Read-only service account, authorized views, row-level security |
| Neo4j in Docker, wiped on each run | Managed graph, incremental MERGE, secrets in Secret Manager |
| Keyword blocklist | Read-only role, compile-checked queries, timeouts |

## Defend it

- Why isn't validation enough without a read-only identity?
- When would you use a graph rather than SQL?
- What goes wrong if the model defines a business metric?
