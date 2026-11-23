"""Inspect chunk boundaries before creating embeddings.

A production RAG team should review chunk quality rather than assuming that a
parser configuration is automatically optimal for every document.
"""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel

from config import OUTPUT_DIR


def main() -> None:
    """Print each parser chunk in a readable form."""
    rows = json.loads((OUTPUT_DIR / "chunks.json").read_text(encoding="utf-8"))
    console = Console()

    for row in rows:
        console.print(
            Panel(
                row["content"],
                title=row["chunk_id"],
                subtitle=f'ordinal={row["ordinal"]}',
            )
        )

    console.print(f"\nTotal chunks: {len(rows)}")
    console.print(
        "Trainer question: Which chunks depend on headings, tables or figures?"
    )


if __name__ == "__main__":
    main()
