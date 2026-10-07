"""Generate Vertex AI embeddings and load chunks into BigQuery.

Engineering intent:
- `RETRIEVAL_DOCUMENT` is used for corpus chunks.
- A reduced output dimensionality keeps this training lab lightweight.
- Metadata remains beside the embedding for filtering and evidence display.
"""

from __future__ import annotations

import json

from google import genai
from google.genai import types
from google.cloud import bigquery

from config import (
    BQ_DATASET,
    BQ_TABLE,
    EMBEDDING_DIMENSION,
    EMBEDDING_LOCATION,
    EMBEDDING_MODEL,
    OUTPUT_DIR,
    PROJECT_ID,
)


def embed_document(client: genai.Client, text: str) -> list[float]:
    """Create one document embedding."""
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBEDDING_DIMENSION,
        ),
    )
    return response.embeddings[0].values


def main() -> None:
    """Embed all parser chunks and replace the lab BigQuery table."""
    chunks = json.loads(
        (OUTPUT_DIR / "chunks.json").read_text(encoding="utf-8")
    )

    embedding_client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=EMBEDDING_LOCATION,
    )
    bq = bigquery.Client(project=PROJECT_ID)

    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
    schema = [
        bigquery.SchemaField("chunk_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("content", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_uri", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("ordinal", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED"),
    ]

    table = bigquery.Table(table_id, schema=schema)
    bq.delete_table(table_id, not_found_ok=True)
    bq.create_table(table)

    rows = []
    for position, chunk in enumerate(chunks, start=1):
        print(f"Embedding {position}/{len(chunks)}: {chunk['chunk_id']}")
        rows.append(
            {
                **chunk,
                "embedding": embed_document(
                    embedding_client,
                    chunk["content"],
                ),
            }
        )

    errors = bq.insert_rows_json(table_id, rows)
    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")

    print(f"Loaded {len(rows)} chunks into {table_id}")


if __name__ == "__main__":
    main()
