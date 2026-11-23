"""Knowledge search over the runbook and postmortem chunks (Gates 4, 5, 10, 12).

    question
      -> current-version filter   only versions the register marks current, read at question time
      -> dense leg                BigQuery VECTOR_SEARCH, top K (finds paraphrases)
      -> lexical leg              exact codes and IDs in the question only, top K (none: dense only)
      -> fusion                   reciprocal rank fusion (RRF, k=60) of the two lists
      -> rerank                   Vertex AI Ranking API, keep top N
      -> abstain                  nothing above MIN_RELEVANCE_SCORE = no evidence, say so

Why the register is checked here and not only at ingest: a chunk's status is
a snapshot from ingest time. If a runbook is withdrawn or superseded, the
register changes at once, and this filter hides the old chunks before anyone
re-ingests (KN-20). The list of current versions is read from the register
(re-read at most every 60 s) and passed as a parameter: BigQuery's
VECTOR_SEARCH doesn't accept a JOIN inside its base query. The register's
fingerprint is part of the cache key, so a cached answer from the old version
is never served (Gate 10).

Why our own lexical leg and RRF instead of a single hybrid query: both legs
are plain SQL we can test and explain, and RRF needs no score calibration
between cosine distance and keyword counts.

Postmortems come back labelled as historical hints. The orchestrator's rules
say a hint is never proof of today's cause.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from common import config, results
from common.clients import query_rows, rank_client, with_retry
from orchestrator.retrieval.cache import TTLCache
from orchestrator.retrieval.embeddings import embed_query

RRF_K = 60
CONTENT_CHARS = 1500           # per evidence chunk sent to the model (context budget, Gate 9)
VERSION_TTL_SECONDS = 60       # how long the index version + register fingerprint are reused

DOC_TYPES = ("runbook", "postmortem")
EXCEPTION_TYPES = ("inventory_shortage", "allocation", "carrier_delay", "payment_hold",
                   "warehouse_disruption", "recent_change")

# Exact codes and IDs: ALLOC-E107, WX-HOLD, PAY-H201, RB-CAR-003, PM-2026-009, WH-BLR-01, SYSTEM_DOWN.
CODE = re.compile(r"\b[A-Z]{2,}(?:[-_][A-Z0-9]+)+\b")
STOPWORDS = set("""about after again also another because been before being between both could does doing
during each from further have having here into just more most only other over same should some such than
that their them then there these they this those through under until very what when where which while
who whom why will with would your what's whats does it's stuck procedure happens happened""".split())

_retrieval_cache = TTLCache("retrieval", config.RETRIEVAL_CACHE_TTL_SECONDS)
_version_lock = threading.Lock()
_version_memo: dict[str, tuple[float, dict]] = {}


# -----------------------------------------------------------------------------
# Query terms
# -----------------------------------------------------------------------------

def exact_codes(question: str) -> list[str]:
    return list(dict.fromkeys(CODE.findall(question)))


def key_words(question: str) -> list[str]:
    words = re.findall(r"[a-z][a-z'-]{3,}", question.lower())
    return list(dict.fromkeys(w.strip("'-") for w in words if w not in STOPWORDS))[:12]


# -----------------------------------------------------------------------------
# Filters: current versions only, same embedding model and dimension
# -----------------------------------------------------------------------------

def _filters(doc_type: str | None, exception_type: str | None, warehouse_id: str | None,
             dimension: int, current_docs: list[str]) -> tuple[str, list, dict]:
    """Plain predicates on the chunk table only (what VECTOR_SEARCH accepts in its base query)."""
    from google.cloud import bigquery

    clauses = ["doc_key IN UNNEST(@current_docs)", "embedding_model = @model", "embedding_dimension = @dimension"]
    params = [bigquery.ArrayQueryParameter("current_docs", "STRING", current_docs),
              bigquery.ScalarQueryParameter("model", "STRING", config.EMBEDDING_MODEL),
              bigquery.ScalarQueryParameter("dimension", "INT64", dimension)]
    readable: dict[str, Any] = {"status": "current"}
    if doc_type:
        clauses.append("doc_type = @doc_type")
        params.append(bigquery.ScalarQueryParameter("doc_type", "STRING", doc_type))
        readable["doc_type"] = doc_type
    if exception_type:
        clauses.append("exception_type = @exception_type")
        params.append(bigquery.ScalarQueryParameter("exception_type", "STRING", exception_type))
        readable["exception_type"] = exception_type
    if warehouse_id:
        # Postmortems name a warehouse; runbooks apply to all, so they stay in.
        clauses.append("(doc_type = 'runbook' OR warehouse_id = @warehouse_id)")
        params.append(bigquery.ScalarQueryParameter("warehouse_id", "STRING", warehouse_id))
        readable["warehouse_id"] = warehouse_id
    return " AND ".join(clauses), params, readable


def _base(table: str, where: str) -> str:
    return f"(SELECT * FROM `{config.table_id(table)}` WHERE {where})"


COLUMNS = ("chunk_id", "doc_id", "version", "doc_type", "title", "section", "content", "exception_type",
           "warehouse_id", "page_start", "page_end", "incident_date", "effective_date", "media")


def knowledge_version(table: str, dimension: int) -> dict:
    """Index version of the chunk table, the register's current versions and their fingerprint (memoized 60 s)."""
    memo_key = f"{table}:{dimension}"
    with _version_lock:
        hit = _version_memo.get(memo_key)
        if hit and time.time() - hit[0] < VERSION_TTL_SECONDS:
            return hit[1]
    from google.cloud import bigquery
    rows = query_rows(f"""
        SELECT
          (SELECT ANY_VALUE(index_version) FROM `{config.table_id(table)}`
            WHERE embedding_model = @model AND embedding_dimension = @dimension) AS index_version,
          (SELECT FARM_FINGERPRINT(STRING_AGG(CONCAT(doc_id, ':', version, ':', status), ',' ORDER BY doc_id, version))
             FROM `{config.table_id(config.BQ_DOCUMENT_REGISTER_TABLE)}`) AS register_fingerprint,
          (SELECT ARRAY_AGG(CONCAT(doc_id, '@v', version) ORDER BY doc_id, version)
             FROM `{config.table_id(config.BQ_DOCUMENT_REGISTER_TABLE)}` WHERE status = 'current') AS current_docs
    """, [bigquery.ScalarQueryParameter("model", "STRING", config.EMBEDDING_MODEL),
          bigquery.ScalarQueryParameter("dimension", "INT64", dimension)], "knowledge_version")
    value = {"index_version": rows[0]["index_version"], "register_fingerprint": str(rows[0]["register_fingerprint"]),
             "current_docs": list(rows[0]["current_docs"] or [])}
    with _version_lock:
        _version_memo[memo_key] = (time.time(), value)
    return value


# -----------------------------------------------------------------------------
# The two legs and the fusion
# -----------------------------------------------------------------------------

def dense_search(vector: list[float], table: str, where: str, params: list, top_k: int) -> list[dict]:
    from google.cloud import bigquery
    select = ", ".join(f"base.{c}" for c in COLUMNS)
    sql = f"""
        SELECT {select}, distance
        FROM VECTOR_SEARCH({_base(table, where)}, 'embedding',
                           (SELECT @v AS embedding), top_k => {int(top_k)}, distance_type => 'COSINE')
        ORDER BY distance"""
    return query_rows(sql, params + [bigquery.ArrayQueryParameter("v", "FLOAT64", vector)], "dense_search")


def lexical_search(codes: list[str], words: list[str], table: str, where: str, params: list,
                   top_k: int) -> list[dict]:
    """Exact codes count 3 (5 if the code is the document ID). No match = not returned.

    search() passes codes only; `words` (each key word counts 1) is kept for experiments: on the
    golden questions, counting key words pushed wordy postmortems above the right runbook.

    IFNULL on section: in BigQuery CONCAT with one NULL is NULL, so a chunk without a heading
    (e.g. OCR text from the scan) would silently never match.
    """
    if not codes and not words:
        return []
    from google.cloud import bigquery
    select = ", ".join(COLUMNS)                    # outer query: the inner alias b is out of scope here
    sql = f"""
        SELECT {select}, score FROM (
          SELECT b.*,
            (SELECT COUNT(*) FROM UNNEST(@codes) AS code
               WHERE STRPOS(UPPER(CONCAT(b.title, ' ', b.content)), code) > 0) * 3
            + IF(b.doc_id IN UNNEST(@codes), 5, 0)
            + (SELECT COUNT(*) FROM UNNEST(@words) AS w
               WHERE STRPOS(LOWER(CONCAT(b.title, ' ', IFNULL(b.section, ''), ' ', b.content)), w) > 0) AS score
          FROM {_base(table, where)} AS b)
        WHERE score > 0
        ORDER BY score DESC, chunk_id
        LIMIT {int(top_k)}"""
    return query_rows(sql, params + [bigquery.ArrayQueryParameter("codes", "STRING", codes),
                                     bigquery.ArrayQueryParameter("words", "STRING", words)], "lexical_search")


def rrf_fuse(dense: list[dict], lexical: list[dict], k: int = RRF_K, limit: int | None = None) -> list[dict]:
    """Reciprocal rank fusion: score = sum of 1 / (k + rank) over the lists a chunk appears in."""
    fused: dict[str, dict] = {}
    for leg, rows in (("dense", dense), ("lexical", lexical)):
        for rank, row in enumerate(rows, start=1):
            item = fused.setdefault(row["chunk_id"], {**row, "rrf": 0.0, "legs": []})
            item["rrf"] += 1.0 / (k + rank)
            item["legs"].append(f"{leg}#{rank}")
    ordered = sorted(fused.values(), key=lambda r: (-r["rrf"], r["chunk_id"]))
    return ordered[:limit] if limit else ordered


def rerank(question: str, candidates: list[dict], top_n: int) -> list[dict]:
    """Vertex AI Ranking API: relevance only (session 8 _rerank_remote)."""
    from google.cloud import discoveryengine_v1 as discoveryengine
    client = rank_client()
    request = discoveryengine.RankRequest(
        ranking_config=client.ranking_config_path(project=config.PROJECT_ID, location="global",
                                                  ranking_config="default_ranking_config"),
        model=config.RANKING_MODEL, top_n=top_n, query=question,
        records=[discoveryengine.RankingRecord(id=c["chunk_id"], title=f"{c['title']} | {c.get('section') or ''}",
                                               content=(c["content"] or "")[:4000]) for c in candidates])
    scores = {r.id: round(float(r.score), 4) for r in with_retry(lambda: client.rank(request=request), "rerank").records}
    by_id = {c["chunk_id"]: c for c in candidates}
    ranked = [dict(by_id[i], relevance=s) for i, s in sorted(scores.items(), key=lambda kv: -kv[1]) if i in by_id]
    return ranked[:top_n]


# -----------------------------------------------------------------------------
# Evidence cards: what the model sees
# -----------------------------------------------------------------------------

def _card(c: dict) -> dict:
    is_postmortem = c["doc_type"] == "postmortem"
    content = (c.get("content") or "").strip()
    return {
        "evidence_id": results.evidence_id("DOC", c["chunk_id"]),
        "doc_id": c["doc_id"],
        "version": c["version"],
        "doc_type": c["doc_type"],
        "title": c["title"],
        "section": c.get("section"),
        "pages": f"{c.get('page_start')}-{c.get('page_end')}",
        "role": ("historical hint: a past incident, never proof of today's cause; confirm with current data"
                 if is_postmortem else "procedure: how to check and who decides, not what is true today"),
        "incident_date": str(c["incident_date"]) if c.get("incident_date") else None,
        "relevance": c.get("relevance"),
        "content": content if len(content) <= CONTENT_CHARS else content[:CONTENT_CHARS] + " …",
    }


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def search(question: str, *, doc_type: str | None = None, exception_type: str | None = None,
           warehouse_id: str | None = None, table: str | None = None, dimension: int | None = None,
           top_k: int | None = None, top_n: int | None = None, use_cache: bool = True,
           use_rerank: bool = True, legs: str = "hybrid") -> dict:
    """Standard result: ok with evidence cards, no_evidence (abstain), or error.

    The "_trace" key carries strategy, cache and candidate details for the
    harness trace and the Gate 2-5 experiments; the plugin strips it before
    the model sees the result. legs = hybrid | dense | lexical (experiments only).
    """
    started = time.perf_counter()
    question = " ".join((question or "").split())
    if len(question) < 3:
        return results.error("knowledge_search", "invalid_argument", "question is empty")
    if doc_type and doc_type not in DOC_TYPES:
        return results.error("knowledge_search", "invalid_argument", f"doc_type must be one of {DOC_TYPES}")
    if legs not in ("hybrid", "dense", "lexical"):
        return results.error("knowledge_search", "invalid_argument", "legs must be hybrid, dense or lexical")
    if exception_type and exception_type not in EXCEPTION_TYPES:
        return results.error("knowledge_search", "invalid_argument",
                             f"exception_type must be one of {EXCEPTION_TYPES}")

    table = table or config.BQ_DOC_CHUNKS_TABLE
    dimension = dimension or config.EMBEDDING_DIMENSION
    top_k = top_k or config.TOP_K
    top_n = top_n or config.TOP_N
    version = knowledge_version(table, dimension)
    where, params, readable = _filters(doc_type, exception_type, warehouse_id, dimension, version["current_docs"])
    if not version["index_version"]:
        return results.error("knowledge_search", "unavailable",
                             f"{table} has no chunks for {config.EMBEDDING_MODEL}@{dimension}; run scripts.ingest_docs")

    key = TTLCache.key(question, readable, table, dimension, top_k, top_n, use_rerank, legs,
                       version["index_version"], version["register_fingerprint"])
    if use_cache:
        cached = _retrieval_cache.get(key)
        if cached is not None:
            return {**cached, "_trace": {**cached["_trace"], "cache": "hit",
                                         "latency_ms": round((time.perf_counter() - started) * 1000)}}

    # Lexical leg = exact codes and IDs only. Measured on the golden questions: counting key words
    # pulled wordy postmortems above the right runbook for paraphrases (P03, P04), while exact
    # codes lifted the right document (E03, E04, PAY-H205). No code in the question: dense only.
    codes, words = exact_codes(question), []
    dense, lexical, embedding_cached = [], [], None
    # The two legs are independent queries: run them side by side (halves the BigQuery wait).
    with ThreadPoolExecutor(max_workers=2) as pool:
        lexical_job = pool.submit(lexical_search, codes, words, table, where, params, top_k) \
            if legs in ("hybrid", "lexical") else None
        if legs in ("hybrid", "dense"):
            vector, embedding_cached = embed_query(question, dimension=dimension)
            dense = dense_search(vector, table, where, params, top_k)
        if lexical_job is not None:
            lexical = lexical_job.result()
    fused = rrf_fuse(dense, lexical, limit=top_k)

    if legs != "hybrid":
        strategy = f"{legs} only (experiment)"
    else:
        strategy = "hybrid (dense + lexical, RRF)" if lexical else "dense only (no exact codes or key words matched)"
    if fused and use_rerank:
        try:
            ranked = rerank(question, fused, top_n)
            strategy += " + rerank"
        except Exception as exc:  # noqa: BLE001 - recorded, and the abstention rule changes
            ranked = [dict(c, relevance=None) for c in fused[:top_n]]
            strategy += f" (rerank unavailable: {type(exc).__name__})"
    else:
        ranked = [dict(c, relevance=None) for c in fused[:top_n]]

    trace = {
        "query_codes": codes, "filters": readable, "strategy": strategy, "cache": "miss",
        "embedding_cache": {True: "hit", False: "miss", None: "n/a"}[embedding_cached],
        "index_version": version["index_version"], "table": table, "dimension": dimension,
        "dense": [r["chunk_id"] for r in dense[:10]], "lexical": [r["chunk_id"] for r in lexical[:10]],
        "fused": [r["chunk_id"] for r in fused[:10]],
        "docs": [f"{c['doc_id']}@v{c['version']}" for c in ranked],
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }

    scored = [c for c in ranked if c["relevance"] is None or c["relevance"] >= config.MIN_RELEVANCE_SCORE]
    if not scored:
        best = max((c["relevance"] or 0 for c in ranked), default=None)
        out = results.no_evidence("knowledge_search",
                                  "No runbook or postmortem section is relevant enough to this question. "
                                  "Say that the documents don't cover it; do not answer from general knowledge.",
                                  data={"best_relevance": best, "threshold": config.MIN_RELEVANCE_SCORE})
    else:
        cards = [_card(c) for c in scored]
        out = results.ok("KNW", key[:12], f"bigquery:{table}",
                         {"query": question, "filters": readable, "strategy": strategy, "results": cards})
    out["_trace"] = trace
    if use_cache:
        _retrieval_cache.put(key, out)
    return out


def cache_stats() -> dict:
    return _retrieval_cache.stats()
