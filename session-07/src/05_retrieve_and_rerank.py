"""CLI demonstration of candidate retrieval followed by Ranking API reranking."""

from __future__ import annotations

import sys

from rag_runtime import rerank, retrieve


def main() -> None:
    """Print retrieval and reranking results side by side."""
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit("Usage: python src/05_retrieve_and_rerank.py <question>")

    candidates = retrieve(question)
    print("\n=== RETRIEVED CANDIDATES ===")
    for item in candidates:
        print(
            f"{item.chunk_id:12} distance={item.retrieval_distance:.4f} "
            f"{item.content[:110]!r}"
        )

    reranked = rerank(question, candidates)
    print("\n=== RERANKED EVIDENCE ===")
    for item in reranked:
        print(
            f"{item.chunk_id:12} rank_score={item.rank_score:.4f} "
            f"{item.content[:110]!r}"
        )


if __name__ == "__main__":
    main()
