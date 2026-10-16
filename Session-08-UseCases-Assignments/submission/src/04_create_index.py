"""Create the vector index on `chunks` (session-07 pattern, decision D24).

The filter columns are stored inside the index, so at production scale the
hard filters run during the search and not after it (§6).

BigQuery refuses an IVF vector index on a table with fewer than 5,000 rows
("Please use VECTOR_SEARCH table-valued function directly"). Our table has a
few hundred, so the script records the index as skipped and search runs
exactly (brute force), which is the right choice at this size anyway.

If an index option is not available in the project, it falls back to a
simpler definition and says which one was created.
"""

from __future__ import annotations

from google.cloud import bigquery

from config import BQ_CHUNKS_TABLE, BQ_DATASET, PROJECT_ID, table_id
from health import Health


INDEX_NAME = "chunks_embedding_index"
MIN_ROWS_IVF = 5000  # BigQuery's minimum for CREATE VECTOR INDEX ... index_type = 'IVF'
STORED = "document_id, product, countries, status, effective_from, valid_to, boilerplate, embedding_model, document_type"

# Tried in order: full definition first, simpler ones if an option is rejected.
DEFINITIONS = [
    # A lexical search column must also be stored in the index.
    ("stored filters + lexical column",
     f"STORING(content, {STORED}) OPTIONS(index_type = 'IVF', distance_type = 'COSINE', lexical_search_columns = ['content'])"),
    ("stored filters", f"STORING({STORED}) OPTIONS(index_type = 'IVF', distance_type = 'COSINE')"),
    ("stored filters without countries",
     "STORING(document_id, product, status, effective_from, valid_to, boilerplate, embedding_model, document_type) "
     "OPTIONS(index_type = 'IVF', distance_type = 'COSINE')"),
    ("plain", "OPTIONS(index_type = 'IVF', distance_type = 'COSINE')"),
]


def main() -> None:
    health = Health("index")
    client = bigquery.Client(project=PROJECT_ID)

    rows_now = client.get_table(table_id(BQ_CHUNKS_TABLE)).num_rows
    if rows_now < MIN_ROWS_IVF:
        print(f"[index] skipped: {rows_now} rows < {MIN_ROWS_IVF} required for an IVF index. "
              "VECTOR_SEARCH runs exactly (brute force), which is the right choice at this size (§6).")
        health.record("vector_index", "pass", value=rows_now, threshold=f">= {MIN_ROWS_IVF} rows to build",
                      details="skipped by design: exact VECTOR_SEARCH below BigQuery's IVF minimum")
        health.save()
        return

    created = None
    for label, definition in DEFINITIONS:
        sql = f"CREATE VECTOR INDEX IF NOT EXISTS {INDEX_NAME} ON `{table_id(BQ_CHUNKS_TABLE)}`(embedding) {definition}"
        try:
            client.query(sql).result()
            created = label
            break
        except Exception as exc:
            errors = getattr(exc, "errors", None) or [{"message": str(exc)}]
            print(f"[index] '{label}' not accepted: {errors[0].get('message', '')[:200]}")

    rows = list(client.query(f"""
        SELECT index_name, index_status, coverage_percentage, last_refresh_time, disable_reason
        FROM `{PROJECT_ID}.{BQ_DATASET}.INFORMATION_SCHEMA.VECTOR_INDEXES`
        WHERE table_name = '{BQ_CHUNKS_TABLE}'
    """).result())
    if not rows:
        health.record("vector_index", "warn", details="no index exists")
        print("[index] no vector index exists")
    for r in rows:
        print(f"[index] {r.index_name}: status={r.index_status} coverage={r.coverage_percentage}% "
              f"disable_reason={r.disable_reason}" + (f" (created as: {created})" if created else ""))
        health.record("vector_index", "pass" if r.index_status == "ACTIVE" else "warn", value=r.coverage_percentage,
                      details=f"status {r.index_status}; {r.disable_reason or 'ok'}; definition: {created or 'existing'}. "
                              "Not required at this size: BigQuery searches exactly.")
    health.save()


if __name__ == "__main__":
    main()
