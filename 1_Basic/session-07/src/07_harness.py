"""Interactive terminal harness for the production RAG pipeline."""

from __future__ import annotations

from rag_runtime import answer


def main() -> None:
    """Run a simple REPL so learners can experiment with the same pipeline."""
    print("Google-Native Production RAG")
    print("Type 'exit' to stop.\n")

    while True:
        question = input("Question> ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue

        response, evidence = answer(question)
        print("\nAnswer:")
        print(response)
        print("\nEvidence:", ", ".join(item.chunk_id for item in evidence))
        print()


if __name__ == "__main__":
    main()
