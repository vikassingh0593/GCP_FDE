"""Bootstrap the complete H2 Compact data foundation.

This script keeps setup intentionally compact while preparing a richer RAG
pipeline for the ADK harness:

    1. Upload the source policy to Cloud Storage.
    2. Chunk and catalog the policy.
    3. Generate embeddings with Vertex AI Gemini Embeddings.
    4. Load the knowledge catalog, chunks, vectors and demo data into BigQuery.
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
# Step A — Upload the source document
# -----------------------------------------------------------------------------

def upload_source() -> str:
    """Upload the policy document and return its GCS URI."""

    bucket = gcs.bucket(BUCKET)
    blob = bucket.blob("knowledge/inventory_policy.txt")
    blob.upload_from_filename(SOURCE_FILE)

    uri = f"gs://{BUCKET}/knowledge/inventory_policy.txt"
    print(f"Uploaded source: {uri}")

    return uri


# -----------------------------------------------------------------------------
# Step B — Build a tiny knowledge catalog
# -----------------------------------------------------------------------------

def build_catalog(source_uri: str) -> list[dict]:
    """Create source-level metadata used to constrain retrieval."""

    return [
        {
            "source_id": "inventory-policy-2026-3",
            "title": "Tredence Retail Inventory Decision Policy",
            "domain": "inventory",
            "document_type": "policy",
            "version": "2026.3",
            "status": "APPROVED",
            "effective_date": "2026-01-01",
            "source_uri": source_uri,
        }
    ]


# -----------------------------------------------------------------------------
# Step C — Chunk and enrich the policy
# -----------------------------------------------------------------------------

def infer_topic(section: str) -> str:
    """Assign a simple catalog topic from the section heading."""

    text = section.lower()

    if "freshness" in text or "offline" in text:
        return "freshness"

    if "reload" in text:
        return "reload_governance"

    if "stockout" in text:
        return "stockout"

    if "unsupported" in text or "action" in text:
        return "actions"

    return "general"


def chunk_policy(text: str) -> list[dict]:
    """Split the short policy by numbered sections.

    Each chunk carries lightweight catalog metadata. This keeps the example
    visible and avoids introducing a separate metadata framework.
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
                "source_id": "inventory-policy-2026-3",
                "section": section,
                "topic": infer_topic(section),
                "content": content,
                "status": "APPROVED",
            }
        )

    return chunks


# -----------------------------------------------------------------------------
# Step D — Generate embeddings outside BigQuery
# -----------------------------------------------------------------------------

def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Generate one Vertex AI embedding per chunk."""

    texts = [
        f"{chunk['section']}\n{chunk['content']}"
        for chunk in chunks
    ]

    response = genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
    )

    for chunk, embedding in zip(chunks, response.embeddings):
        chunk["embedding"] = list(embedding.values)

    print(f"Generated {len(chunks)} embeddings using {EMBEDDING_MODEL}.")

    return chunks


# -----------------------------------------------------------------------------
# Step E — Create BigQuery tables
# -----------------------------------------------------------------------------

def create_tables() -> None:
    """Create the knowledge catalog, chunk store and demo operational table."""

    sql = f"""
    CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.knowledge_catalog` (
        source_id STRING,
        title STRING,
        domain STRING,
        document_type STRING,
        version STRING,
        status STRING,
        effective_date DATE,
        source_uri STRING
    );

    CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.knowledge_chunks` (
        chunk_id STRING,
        source_id STRING,
        section STRING,
        topic STRING,
        content STRING,
        status STRING,
        embedding ARRAY<FLOAT64>
    );

    CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.store_metrics` AS
    SELECT *
    FROM UNNEST([
        STRUCT(
            'STORE-101' AS store_id,
            'SKU-0921' AS sku,
            42 AS on_hand,
            8 AS reserved,
            2 AS damaged,
            18 AS projected_demand_6h
        ),
        STRUCT(
            'STORE-205' AS store_id,
            'SKU-0921' AS sku,
            10 AS on_hand,
            9 AS reserved,
            2 AS damaged,
            22 AS projected_demand_6h
        ),
        STRUCT(
            'STORE-309' AS store_id,
            'SKU-0921' AS sku,
            6 AS on_hand,
            4 AS reserved,
            1 AS damaged,
            7 AS projected_demand_6h
        )
    ]);
    """

    bq.query(sql).result()


# -----------------------------------------------------------------------------
# Step F — Load catalog and chunks
# -----------------------------------------------------------------------------

def load_catalog(rows: list[dict]) -> None:
    """Load source-level metadata into BigQuery."""

    table = f"{PROJECT}.{DATASET}.knowledge_catalog"
    errors = bq.insert_rows_json(table, rows)

    if errors:
        raise RuntimeError(f"Knowledge catalog insert failed: {errors}")

    print(f"Loaded {len(rows)} catalog record into {table}.")


def load_chunks(chunks: list[dict]) -> None:
    """Load enriched chunks and their embeddings into BigQuery."""

    table = f"{PROJECT}.{DATASET}.knowledge_chunks"
    errors = bq.insert_rows_json(table, chunks)

    if errors:
        raise RuntimeError(f"Knowledge chunk insert failed: {errors}")

    print(f"Loaded {len(chunks)} chunks into {table}.")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> None:
    print("\n=== H2 Compact Bootstrap — Enhanced RAG ===\n")

    source_uri = upload_source()
    source_text = SOURCE_FILE.read_text(encoding="utf-8")

    catalog = build_catalog(source_uri)
    chunks = chunk_policy(source_text)
    chunks = embed_chunks(chunks)

    create_tables()
    load_catalog(catalog)
    load_chunks(chunks)

    print("\nBootstrap complete.")
    print(f"Dataset : {PROJECT}.{DATASET}")
    print(f"Catalog : {PROJECT}.{DATASET}.knowledge_catalog")
    print(f"Chunks  : {PROJECT}.{DATASET}.knowledge_chunks")
    print(f"Bucket  : gs://{BUCKET}")
    print("\nNext: cd 03_HARNESS && adk web --port 8080\n")


if __name__ == "__main__":
    main()
