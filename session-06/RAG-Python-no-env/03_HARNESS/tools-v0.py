"""Specialist capabilities used by the H2 Compact ADK harness."""

from __future__ import annotations

import math
import os
import re

from google import genai
from google.cloud import bigquery


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "tredence-learning")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
DATASET = os.getenv("H2_COMPACT_DATASET", "tredence_fde_h2_compact")
EMBEDDING_MODEL = os.getenv("H2_EMBEDDING_MODEL", "gemini-embedding-001")

bq = bigquery.Client(project=PROJECT)
genai_client = genai.Client(
    vertexai=True,
    project=PROJECT,
    location=LOCATION,
)


# -----------------------------------------------------------------------------
# Small retrieval helpers
# -----------------------------------------------------------------------------

STOP_WORDS = {
    "the", "and", "for", "that", "this", "with", "what", "when",
    "where", "which", "from", "into", "about", "should", "would",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9-]+", text.lower())
    return {word for word in words if len(word) > 2 and word not in STOP_WORDS}


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))

    denominator = left_norm * right_norm
    return numerator / denominator if denominator else 0.0


def _lexical_score(question: str, document: str) -> float:
    query_tokens = _tokens(question)
    document_tokens = _tokens(document)

    if not query_tokens:
        return 0.0

    overlap = len(query_tokens & document_tokens)
    return overlap / len(query_tokens)


# -----------------------------------------------------------------------------
# Hybrid RAG
# -----------------------------------------------------------------------------

def hybrid_policy_search(question: str, top_k: int = 3) -> dict:
    """Retrieve policy evidence using lexical + semantic signals.

    Retrieval is intentionally easy to explain:

        hybrid score = 40% lexical + 60% vector similarity

    Embeddings were generated with Vertex AI and stored in BigQuery during
    bootstrap. BigQuery remains the knowledge store; ranking is visible Python.
    """

    query_embedding_response = genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[question],
    )
    query_vector = list(query_embedding_response.embeddings[0].values)

    sql = f"""
        SELECT
            chunk_id,
            section,
            content,
            source_uri,
            embedding
        FROM `{PROJECT}.{DATASET}.knowledge_chunks`
        WHERE status = 'APPROVED'
    """

    rows = list(bq.query(sql).result())
    ranked = []

    for row in rows:
        document = f"{row.section}\n{row.content}"

        lexical = _lexical_score(question, document)
        vector = _cosine_similarity(query_vector, list(row.embedding))
        hybrid = (0.40 * lexical) + (0.60 * max(vector, 0.0))

        ranked.append(
            {
                "chunk_id": row.chunk_id,
                "section": row.section,
                "content": row.content,
                "source_uri": row.source_uri,
                "lexical_score": round(lexical, 4),
                "vector_score": round(vector, 4),
                "hybrid_score": round(hybrid, 4),
            }
        )

    ranked.sort(key=lambda item: item["hybrid_score"], reverse=True)

    return {
        "strategy": "HYBRID",
        "formula": "0.40 lexical + 0.60 vector",
        "evidence": ranked[:top_k],
    }


# -----------------------------------------------------------------------------
# Text-to-SQL plug
# -----------------------------------------------------------------------------

def text_to_sql(question: str) -> dict:
    """Reserved specialist capability for the next lab increment.

    The route exists today, but deliberately generates neither SQL nor results.
    Tomorrow this function can be replaced without redesigning the orchestrator.
    """

    return {
        "capability": "TEXT_TO_SQL",
        "status": "NOT_IMPLEMENTED_YET",
        "question": question,
        "message": (
            "Text-to-SQL route selected. This capability is intentionally "
            "reserved for the next lab increment. No SQL was generated or run."
        ),
    }
