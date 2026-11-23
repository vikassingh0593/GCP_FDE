"""Specialist capabilities used by the H2 Compact ADK harness.

The RAG path intentionally remains one tool from ADK's point of view, but the
inside of that tool now demonstrates a production-style retrieval pipeline:

    query understanding
        -> knowledge catalog
        -> lexical + vector retrieval
        -> hybrid fusion
        -> Gemini reranking
        -> confidence / abstention
        -> grounded evidence
"""

from __future__ import annotations

import json
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

AGENT_MODEL = os.getenv("H2_AGENT_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL = os.getenv("H2_EMBEDDING_MODEL", "gemini-embedding-001")

LEXICAL_WEIGHT = 0.40
VECTOR_WEIGHT = 0.60
RETRIEVE_TOP_K = 5
FINAL_TOP_K = 3
MIN_HYBRID_SCORE = 0.25

bq = bigquery.Client(project=PROJECT)
genai_client = genai.Client(
    vertexai=True,
    project=PROJECT,
    location=LOCATION,
)


# -----------------------------------------------------------------------------
# Retrieval helpers
# -----------------------------------------------------------------------------

STOP_WORDS = {
    "the", "and", "for", "that", "this", "with", "what", "when",
    "where", "which", "from", "into", "about", "should", "would",
}


def _tokens(text: str) -> set[str]:
    """Convert text into a small set of useful lexical tokens."""

    words = re.findall(r"[a-z0-9-]+", text.lower())

    return {
        word
        for word in words
        if len(word) > 2 and word not in STOP_WORDS
    }


def _lexical_score(question: str, document: str) -> float:
    """Measure simple query-token overlap."""

    query_tokens = _tokens(question)
    document_tokens = _tokens(document)

    if not query_tokens:
        return 0.0

    overlap = len(query_tokens & document_tokens)

    return overlap / len(query_tokens)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Calculate cosine similarity between two embedding vectors."""

    numerator = sum(a * b for a, b in zip(left, right))

    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))

    denominator = left_norm * right_norm

    return numerator / denominator if denominator else 0.0


# -----------------------------------------------------------------------------
# 1. Query understanding
# -----------------------------------------------------------------------------

def _understand_query(question: str) -> dict:
    """Extract lightweight catalog hints before retrieval.

    This is deliberately deterministic and visible. The ADK agent handles
    high-level intent; this helper only narrows the knowledge universe.
    """

    text = question.lower()

    filters = {
        "domain": None,
        "document_type": None,
        "topic": None,
    }

    if any(word in text for word in ["inventory", "stock", "sku", "store"]):
        filters["domain"] = "inventory"

    if any(word in text for word in ["policy", "rule", "allowed", "permitted"]):
        filters["document_type"] = "policy"

    if any(word in text for word in ["fresh", "stale", "old", "age", "offline"]):
        filters["topic"] = "freshness"

    elif any(word in text for word in ["reload", "refresh"]):
        filters["topic"] = "reload_governance"

    elif any(word in text for word in ["stockout", "demand", "inbound"]):
        filters["topic"] = "stockout"

    elif any(word in text for word in ["transfer", "unsupported", "action"]):
        filters["topic"] = "actions"

    return {
        "original_query": question,
        "filters": filters,
    }


# -----------------------------------------------------------------------------
# 2. Knowledge catalog filtering
# -----------------------------------------------------------------------------

def _load_catalog_candidates(filters: dict) -> list:
    """Load approved chunks from the relevant catalog area.

    The catalog and chunk tables are joined so retrieval can use source-level
    metadata such as domain, document type and version.
    """

    sql = f"""
        SELECT
            c.chunk_id,
            c.section,
            c.topic,
            c.content,
            c.embedding,
            k.source_id,
            k.title,
            k.domain,
            k.document_type,
            k.version,
            k.source_uri
        FROM
            `{PROJECT}.{DATASET}.knowledge_chunks` AS c
        JOIN
            `{PROJECT}.{DATASET}.knowledge_catalog` AS k
        ON
            c.source_id = k.source_id
        WHERE
            c.status = 'APPROVED'
            AND k.status = 'APPROVED'
    """

    rows = list(bq.query(sql).result())
    candidates = []

    for row in rows:

        if filters.get("domain") and row.domain != filters["domain"]:
            continue

        if (
            filters.get("document_type")
            and row.document_type != filters["document_type"]
        ):
            continue

        if filters.get("topic") and row.topic != filters["topic"]:
            continue

        candidates.append(row)

    return candidates


# -----------------------------------------------------------------------------
# 3. Hybrid retrieval
# -----------------------------------------------------------------------------

def _hybrid_retrieve(
    question: str,
    candidates: list,
    top_k: int = RETRIEVE_TOP_K,
) -> list[dict]:
    """Combine lexical relevance and vector similarity."""

    response = genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[question],
    )

    query_vector = list(response.embeddings[0].values)
    ranked = []

    for row in candidates:
        document = f"{row.section}\n{row.content}"

        lexical = _lexical_score(question, document)
        vector = _cosine_similarity(
            query_vector,
            list(row.embedding),
        )

        hybrid = (
            LEXICAL_WEIGHT * lexical
            + VECTOR_WEIGHT * max(vector, 0.0)
        )

        ranked.append(
            {
                "chunk_id": row.chunk_id,
                "source_id": row.source_id,
                "title": row.title,
                "section": row.section,
                "topic": row.topic,
                "version": row.version,
                "source_uri": row.source_uri,
                "content": row.content,
                "lexical_score": round(lexical, 4),
                "vector_score": round(vector, 4),
                "hybrid_score": round(hybrid, 4),
            }
        )

    ranked.sort(
        key=lambda item: item["hybrid_score"],
        reverse=True,
    )

    return ranked[:top_k]


# -----------------------------------------------------------------------------
# 4. Gemini reranker
# -----------------------------------------------------------------------------

def _rerank(question: str, candidates: list[dict]) -> list[dict]:
    """Use Gemini to reorder retrieved candidates by direct answer relevance.

    If the reranker response cannot be parsed, the original hybrid order is
    retained. Retrieval therefore remains usable even if reranking fails.
    """

    if not candidates:
        return []

    candidate_text = "\n\n".join(
        (
            f"ID: {item['chunk_id']}\n"
            f"Section: {item['section']}\n"
            f"Content: {item['content']}"
        )
        for item in candidates
    )

    prompt = f"""
You are a retrieval reranker.

Rank the candidate chunks by how directly they help answer the question.
Do not answer the question.
Do not add chunk IDs that are not present below.

Return ONLY a JSON array of chunk IDs in best-first order.

Question:
{question}

Candidates:
{candidate_text}
"""

    try:
        response = genai_client.models.generate_content(
            model=AGENT_MODEL,
            contents=prompt,
        )

        text = response.text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)

        ordered_ids = json.loads(text)

        if not isinstance(ordered_ids, list):
            return candidates[:FINAL_TOP_K]

        by_id = {
            item["chunk_id"]: item
            for item in candidates
        }

        reranked = [
            by_id[chunk_id]
            for chunk_id in ordered_ids
            if chunk_id in by_id
        ]

        # Keep any omitted candidates at the end in their original order.
        seen = {item["chunk_id"] for item in reranked}

        reranked.extend(
            item
            for item in candidates
            if item["chunk_id"] not in seen
        )

        return reranked[:FINAL_TOP_K]

    except Exception:
        # Reranking is an enhancement, not a single point of failure.
        return candidates[:FINAL_TOP_K]


# -----------------------------------------------------------------------------
# Public Hybrid RAG tool
# -----------------------------------------------------------------------------

def hybrid_policy_search(question: str, top_k: int = FINAL_TOP_K) -> dict:
    """Retrieve policy evidence through the enhanced RAG pipeline.

    Pipeline:
        query understanding
        -> catalog filtering
        -> lexical + vector hybrid retrieval
        -> Gemini reranking
        -> confidence / abstention
    """

    # 1. Understand the retrieval need.
    query = _understand_query(question)

    # 2. Narrow the search space using the knowledge catalog.
    candidates = _load_catalog_candidates(query["filters"])

    # 3. Retrieve broadly using lexical + semantic signals.
    retrieved = _hybrid_retrieve(
        question=question,
        candidates=candidates,
        top_k=RETRIEVE_TOP_K,
    )

    # 4. Refuse to invent evidence when retrieval is weak.
    best_score = retrieved[0]["hybrid_score"] if retrieved else 0.0

    if best_score < MIN_HYBRID_SCORE:
        return {
            "strategy": "CATALOG_FILTERED_HYBRID_RAG",
            "catalog_filters": query["filters"],
            "candidate_count": len(candidates),
            "retrieved_count": len(retrieved),
            "confidence": "LOW",
            "reranker": "SKIPPED",
            "evidence": [],
            "message": (
                "No sufficiently relevant approved knowledge was found. "
                "Do not fabricate a policy answer."
            ),
        }

    # 5. Rerank the strongest hybrid candidates for final evidence quality.
    evidence = _rerank(
        question=question,
        candidates=retrieved,
    )[:top_k]

    return {
        "strategy": "CATALOG_FILTERED_HYBRID_RAG",
        "formula": "0.40 lexical + 0.60 vector",
        "catalog_filters": query["filters"],
        "candidate_count": len(candidates),
        "retrieved_count": len(retrieved),
        "reranker": "GEMINI",
        "confidence": "HIGH" if best_score >= 0.40 else "MEDIUM",
        "evidence": evidence,
    }


# -----------------------------------------------------------------------------
# Text-to-SQL plug
# -----------------------------------------------------------------------------

def text_to_sql(question: str) -> dict:
    """Reserved specialist capability for the next lab increment."""

    return {
        "capability": "TEXT_TO_SQL",
        "status": "NOT_IMPLEMENTED_YET",
        "question": question,
        "message": (
            "Text-to-SQL route selected. This capability is intentionally "
            "reserved for the next lab increment. No SQL was generated or run."
        ),
    }
