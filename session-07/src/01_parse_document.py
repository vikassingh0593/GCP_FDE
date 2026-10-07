"""Parse the complex PDF with Document AI Layout Parser.

Outputs:
- output/chunks.json       machine-friendly chunks for later stages
- output/parsed_document.md human-readable inspection artifact

The parser is asked to annotate tables/images and create context-aware chunks.
"""

from __future__ import annotations

import json

from google.cloud import documentai

from config import (
    CHUNK_SIZE,
    DOCUMENT_AI_LOCATION,
    GCS_SOURCE_URI,
    INCLUDE_ANCESTOR_HEADINGS,
    OUTPUT_DIR,
    PROCESSOR_ID_FILE,
    PROCESSOR_VERSION,
    PROJECT_ID,
)


def build_client() -> documentai.DocumentProcessorServiceClient:
    """Create a regional Document AI client."""
    return documentai.DocumentProcessorServiceClient(
        client_options={
            "api_endpoint": f"{DOCUMENT_AI_LOCATION}-documentai.googleapis.com"
        }
    )


def main() -> None:
    """Process the PDF and export RAG-ready chunks."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    processor_id = PROCESSOR_ID_FILE.read_text(encoding="utf-8").strip()

    client = build_client()
    name = client.processor_version_path(
        PROJECT_ID,
        DOCUMENT_AI_LOCATION,
        processor_id,
        PROCESSOR_VERSION,
    )

    process_options = documentai.ProcessOptions(
        layout_config=documentai.ProcessOptions.LayoutConfig(
            enable_table_annotation=True,
            enable_image_annotation=True,
            chunking_config=documentai.ProcessOptions.LayoutConfig.ChunkingConfig(
                chunk_size=CHUNK_SIZE,
                include_ancestor_headings=INCLUDE_ANCESTOR_HEADINGS,
            ),
        )
    )

    request = documentai.ProcessRequest(
        name=name,
        gcs_document=documentai.GcsDocument(
            gcs_uri=GCS_SOURCE_URI,
            mime_type="application/pdf",
        ),
        process_options=process_options,
    )

    print("Calling Document AI Layout Parser...")
    result = client.process_document(request=request)
    document = result.document

    rows = []
    markdown_parts = [
        "# Parsed Document — Human Inspection View",
        "",
        f"Source: `{GCS_SOURCE_URI}`",
        "",
        "The sections below are parser-produced RAG chunks.",
        "",
    ]

    for index, chunk in enumerate(document.chunked_document.chunks):
        chunk_id = f"chunk-{index:04d}"
        content = chunk.content.strip()
        if not content:
            continue

        rows.append(
            {
                "chunk_id": chunk_id,
                "content": content,
                "source_uri": GCS_SOURCE_URI,
                "ordinal": index,
            }
        )
        markdown_parts.extend(
            [
                f"## {chunk_id}",
                "",
                content,
                "",
                "---",
                "",
            ]
        )

    (OUTPUT_DIR / "chunks.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "parsed_document.md").write_text(
        "\n".join(markdown_parts),
        encoding="utf-8",
    )

    print(f"Chunks exported: {len(rows)}")
    print("Inspect output/parsed_document.md before continuing.")


if __name__ == "__main__":
    main()
