"""Create a BigQuery vector index with lexical information.

Hybrid retrieval in BigQuery is currently Preview. The index stores the
content column so it can participate in the lexical side of hybrid search.
"""

from __future__ import annotations

from google.cloud import bigquery

from config import BQ_DATASET, BQ_TABLE, PROJECT_ID


def main() -> None:
    """Create or replace the lab vector index."""
    client = bigquery.Client(project=PROJECT_ID)
    table_id = f"`{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}`"

    sql = f"""
    CREATE OR REPLACE VECTOR INDEX rag_hybrid_index
    ON {table_id}(embedding)
    STORING(chunk_id, content, source_uri, ordinal)
    OPTIONS(
      index_type='IVF',
      distance_type='COSINE',
      lexical_search_columns=['content']
    )
    """
    client.query(sql).result()
    print("Vector/hybrid index creation submitted successfully.")
    print(
        "Note: on a tiny training table BigQuery may still use brute force; "
        "the index exists to teach the production pattern."
    )


if __name__ == "__main__":
    main()
