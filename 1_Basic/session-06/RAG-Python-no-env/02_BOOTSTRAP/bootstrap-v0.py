"""Bootstrap the complete H2 Compact data foundation.

One script intentionally performs the infrastructure-facing preparation so the
live class can focus on the harness rather than repetitive setup mechanics.

It performs four visible operations:
    1. Upload the source policy to Cloud Storage.
    2. Chunk the policy into small sections.
    3. Generate embeddings with Vertex AI Gemini Embeddings.
    4. Load knowledge and demo operational data into BigQuery.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from google import genai
from google.cloud import bigquery, storage


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "tredence-learning")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
DATASET = os.getenv("H2_COMPACT_DATASET", "tredence_fde_h2_compact")
BUCKET = os.getenv(
    "H2_COMPACT_BUCKET",
    f"{PROJECT}-tredence-fde-h2-compact",
)
EMBEDDING_MODEL = os.getenv("H2_EMBEDDING_MODEL", "gemini-embedding-001")

HERE = Path(__file__).resolve().parent
SOURCE_FILE = HERE / "source_docs" / "inventory_policy.txt"

bq = bigquery.Client(project=PROJECT)
gcs = storage.Client(project=PROJECT)
genai_client = genai.Client(
    vertexai=True,
    project=PROJECT,
    location=LOCATION,
)


# -----------------------------------------------------------------------------
# Step A — Upload source document
# -----------------------------------------------------------------------------

def upload_source() -> str:
    bucket = gcs.bucket(BUCKET)
    blob = bucket.blob("knowledge/inventory_policy.txt")
    blob.upload_from_filename(SOURCE_FILE)

    uri = f"gs://{BUCKET}/knowledge/inventory_policy.txt"
    print(f"Uploaded source: {uri}")
    return uri


# -----------------------------------------------------------------------------
# Step B — Chunk document
# -----------------------------------------------------------------------------

def chunk_policy(text: str) -> list[dict]:
    """Split the short policy by numbered sections.

    The chunking is deliberately transparent for classroom explanation.
    """

    parts = re.split(r"\n(?=\d+\.\s)", text.strip())
    chunks = []

    for index, part in enumerate(parts[1:], start=1):
        lines = [line.strip() for line in part.splitlines() if line.strip()]
        section = lines[0]
        content = " ".join(lines[1:])

        chunks.append(
            {
                "chunk_id": f"POL-{index:03d}",
                "section": section,
                "content": content,
                "status": "APPROVED",
            }
        )

    return chunks


# -----------------------------------------------------------------------------
# Step C — Generate embeddings outside BigQuery
# -----------------------------------------------------------------------------

def embed_chunks(chunks: list[dict]) -> list[dict]:
    texts = [f"{chunk['section']}\n{chunk['content']}" for chunk in chunks]

    response = genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
    )

    for chunk, embedding in zip(chunks, response.embeddings):
        chunk["embedding"] = list(embedding.values)

    print(f"Generated {len(chunks)} embeddings using {EMBEDDING_MODEL}.")
    return chunks


# -----------------------------------------------------------------------------
# Step D — Load BigQuery tables
# -----------------------------------------------------------------------------

def create_tables() -> None:
    sql = f"""
    CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.knowledge_chunks` (
        chunk_id STRING,
        section STRING,
        content STRING,
        status STRING,
        source_uri STRING,
        embedding ARRAY<FLOAT64>
    );

    CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.store_metrics` AS
    SELECT * FROM UNNEST([
        STRUCT('STORE-101' AS store_id, 'SKU-0921' AS sku, 42 AS on_hand, 8 AS reserved, 2 AS damaged, 18 AS projected_demand_6h),
        STRUCT('STORE-205' AS store_id, 'SKU-0921' AS sku, 10 AS on_hand, 9 AS reserved, 2 AS damaged, 22 AS projected_demand_6h),
        STRUCT('STORE-309' AS store_id, 'SKU-0921' AS sku, 6 AS on_hand, 4 AS reserved, 1 AS damaged, 7 AS projected_demand_6h)
    ]);
    """

    bq.query(sql).result()


def load_chunks(chunks: list[dict], source_uri: str) -> None:
    rows = []

    for chunk in chunks:
        rows.append(
            {
                **chunk,
                "source_uri": source_uri,
            }
        )

    table = f"{PROJECT}.{DATASET}.knowledge_chunks"
    errors = bq.insert_rows_json(table, rows)

    if errors:
        raise RuntimeError(f"BigQuery insert failed: {errors}")

    print(f"Loaded {len(rows)} chunks into {table}.")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> None:
    print("\n=== H2 Compact Bootstrap ===\n")

    source_uri = upload_source()
    source_text = SOURCE_FILE.read_text(encoding="utf-8")

    chunks = chunk_policy(source_text)
    chunks = embed_chunks(chunks)

    create_tables()
    load_chunks(chunks, source_uri)

    print("\nBootstrap complete.")
    print(f"Dataset: {PROJECT}.{DATASET}")
    print(f"Bucket : gs://{BUCKET}")
    print("\nNext: cd 03_HARNESS && adk web --port 8001\n")


if __name__ == "__main__":
    main()
