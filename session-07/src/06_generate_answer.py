"""Run the full RAG path for one question and show the supporting evidence."""

from __future__ import annotations

import sys

from rag_runtime import answer


def main() -> None:
    """Answer one CLI question."""
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit("Usage: python src/06_generate_answer.py <question>")

    response, evidence = answer(question)

    print("\n=== ANSWER ===")
    print(response)
    print("\n=== FINAL EVIDENCE ===")
    for item in evidence:
        print(
            f"- {item.chunk_id} "
            f"(rank={item.rank_score:.4f}, distance={item.retrieval_distance:.4f})"
        )


if __name__ == "__main__":
    main()
