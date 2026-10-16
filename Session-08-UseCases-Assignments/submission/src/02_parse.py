"""Parse the allowlisted files with Document AI Layout Parser.

For each file in SOURCE_FILES:
1. Call Layout Parser online. If Document AI rejects the file (for example,
   too many pages for an online call), switch to batch processing for that
   file automatically (decision D5).
2. Save the raw response in output/parsed/, keyed by the file's MD5 and the
   parse settings. A re-run with the same file and settings reuses it and
   does not call Document AI again (decision D9).
3. Turn Layout Parser's chunks into our chunk rows: document ID (from the
   BigQuery `documents` table), page span, position, and the types of the
   layout blocks each chunk was built from.

Output: output/chunks_cs<size>.json, checked next by 02a_check_parse.py.

Usage:
    python src/02_parse.py                    # all files, CHUNK_SIZE from env.sh
    python src/02_parse.py --chunk-size 256   # the chunk-size experiment (D6)
    python src/02_parse.py --file HN-204_Clinical_Study.pdf

Pattern from session-07/src/01_parse_document.py, extended to many files,
two file types, caching, batch fallback and page numbers on every chunk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone

from google.api_core.exceptions import InvalidArgument
from google.cloud import bigquery, documentai, storage

from config import (
    BQ_DOCUMENTS_TABLE,
    CHUNK_SIZE,
    CORPUS_DIR,
    DOCUMENT_AI_LOCATION,
    GCS_BUCKET,
    INCLUDE_ANCESTOR_HEADINGS,
    OUTPUT_DIR,
    PROCESSOR_ID_FILE,
    PROCESSOR_VERSION,
    PROJECT_ID,
    SOURCE_FILES,
    gcs_uri,
    table_id,
)


PARSED_DIR = OUTPUT_DIR / "parsed"

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Session-07 settings, kept for this first run (decision D7). Both produce
# model-generated descriptions, which 02a_check_parse.py looks for so we can
# decide whether they can be tagged `generated` or must be switched off.
ENABLE_TABLE_ANNOTATION = True
ENABLE_IMAGE_ANNOTATION = True


# -----------------------------------------------------------------------------
# Document AI
# -----------------------------------------------------------------------------

def _client() -> documentai.DocumentProcessorServiceClient:
    """Document AI is regional, so the client must use the regional endpoint."""
    return documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{DOCUMENT_AI_LOCATION}-documentai.googleapis.com"}
    )


def _processor_version_name(client) -> str:
    """Full resource name of our processor, pinned to one version."""
    processor_id = PROCESSOR_ID_FILE.read_text(encoding="utf-8").strip()
    return client.processor_version_path(PROJECT_ID, DOCUMENT_AI_LOCATION, processor_id, PROCESSOR_VERSION)


def _process_options(chunk_size: int) -> documentai.ProcessOptions:
    """Layout Parser options: annotations plus its built-in, layout-aware chunking."""
    return documentai.ProcessOptions(
        layout_config=documentai.ProcessOptions.LayoutConfig(
            enable_table_annotation=ENABLE_TABLE_ANNOTATION,
            enable_image_annotation=ENABLE_IMAGE_ANNOTATION,
            chunking_config=documentai.ProcessOptions.LayoutConfig.ChunkingConfig(
                chunk_size=chunk_size,
                include_ancestor_headings=INCLUDE_ANCESTOR_HEADINGS,
            ),
        )
    )


def _parse_online(client, name: str, uri: str, mime: str, options) -> dict:
    """One synchronous call; the response comes back directly."""
    request = documentai.ProcessRequest(
        name=name,
        gcs_document=documentai.GcsDocument(gcs_uri=uri, mime_type=mime),
        process_options=options,
    )
    document = client.process_document(request=request).document
    return json.loads(documentai.Document.to_json(document))


def _parse_batch(client, name: str, uri: str, mime: str, options, stem: str, chunk_size: int) -> dict:
    """Asynchronous call for files the online call rejects.

    Document AI writes the result as JSON shards to Cloud Storage; we read the
    shards back and join their chunks and layout blocks in order.
    """
    output_prefix = f"gs://{GCS_BUCKET}/parsed/{stem}/cs{chunk_size}/"
    request = documentai.BatchProcessRequest(
        name=name,
        input_documents=documentai.BatchDocumentsInputConfig(
            gcs_documents=documentai.GcsDocuments(
                documents=[documentai.GcsDocument(gcs_uri=uri, mime_type=mime)]
            )
        ),
        document_output_config=documentai.DocumentOutputConfig(
            gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(gcs_uri=output_prefix)
        ),
        process_options=options,
    )
    operation = client.batch_process_documents(request=request)
    print("         batch job started, waiting...")
    operation.result(timeout=1200)

    metadata = documentai.BatchProcessMetadata(operation.metadata)
    destination = metadata.individual_process_statuses[0].output_gcs_destination
    bucket_name, prefix = destination.removeprefix("gs://").split("/", 1)
    shards = sorted(
        (b for b in storage.Client(project=PROJECT_ID).list_blobs(bucket_name, prefix=prefix) if b.name.endswith(".json")),
        key=lambda b: b.name,
    )
    merged: dict = {}
    for blob in shards:
        part = json.loads(blob.download_as_bytes())
        if not merged:
            merged = part
            continue
        merged.setdefault("chunkedDocument", {}).setdefault("chunks", []).extend(
            part.get("chunkedDocument", {}).get("chunks", [])
        )
        merged.setdefault("documentLayout", {}).setdefault("blocks", []).extend(
            part.get("documentLayout", {}).get("blocks", [])
        )
    print(f"         batch output: {len(shards)} shard(s) from {destination}")
    return merged


# -----------------------------------------------------------------------------
# Layout blocks and chunks
# -----------------------------------------------------------------------------

def _index_blocks(blocks: list[dict], index: dict) -> None:
    """Map every layout block ID (including nested ones) to its kind.

    Kinds come from the block's key, e.g. textBlock → "text/heading-1",
    tableBlock → "table". Unknown kinds (e.g. image blocks) are kept as-is
    so the check script can see them.
    """
    for block in blocks:
        kind = next((k for k in block if k.endswith("Block")), "unknown")
        detail = block.get(kind, {})
        label = kind.removesuffix("Block")
        if kind == "textBlock" and detail.get("type"):
            label = f"text/{detail['type']}"
        index[block.get("blockId", "")] = label
        _index_blocks(detail.get("blocks", []), index)


# Layout Parser writes image descriptions (model-generated) into the chunk
# text between these markers. We move them out of `content` into
# `annotations`, so generated text is tagged, never mixed with document text,
# and never dilutes the chunk's embedding (decision D7, §3 chart rule).
ANNOTATION = re.compile(r"__START_OF_ANNOTATION__(.*?)__END_OF_ANNOTATION__", re.S)


def _chunk_rows(document_id: str, filename: str, chunk_size: int, raw: dict) -> list[dict]:
    """Our chunk rows from Layout Parser's chunks."""
    block_kinds: dict = {}
    _index_blocks(raw.get("documentLayout", {}).get("blocks", []), block_kinds)

    rows = []
    for position, chunk in enumerate(raw.get("chunkedDocument", {}).get("chunks", [])):
        raw_content = chunk.get("content", "")
        annotations = [a.strip() for a in ANNOTATION.findall(raw_content) if a.strip()]
        content = ANNOTATION.sub("", raw_content).strip()
        if not content and not annotations:
            continue
        span = chunk.get("pageSpan", {})
        rows.append({
            "chunk_id": f"{document_id}-c{position:04d}",
            "document_id": document_id,
            "filename": filename,
            "chunk_size": chunk_size,
            "position": position,
            "page_start": span.get("pageStart"),
            "page_end": span.get("pageEnd"),
            "block_kinds": sorted({block_kinds.get(b, "unknown") for b in chunk.get("sourceBlockIds", [])}),
            "content": content,
            "annotations": annotations,  # generated by the parser's model, not document text
            # Running page headers are kept apart from the text by Layout Parser
            # (e.g. the scanned letters' "SCANNED HISTORICAL AX-17 SAFETY LETTER - PAGE 1").
            "page_headers": [h.get("text", "").strip() for h in chunk.get("pageHeaders", []) if h.get("text", "").strip()],
        })
    return rows


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def _document_ids() -> dict:
    """filename → document_id, from the BigQuery registry (source of truth)."""
    rows = bigquery.Client(project=PROJECT_ID).query(
        f"SELECT filename, document_id FROM `{table_id(BQ_DOCUMENTS_TABLE)}`"
    ).result()
    return {r.filename: r.document_id for r in rows}


def parse_file(client, name: str, filename: str, chunk_size: int) -> tuple[dict, str]:
    """Return the raw Layout Parser result for one file, from cache if possible."""
    path = CORPUS_DIR / filename
    md5 = hashlib.md5(path.read_bytes()).hexdigest()
    stem = path.stem
    cache = PARSED_DIR / f"{stem}__cs{chunk_size}__{md5[:12]}.json"

    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["document"], "cache"

    uri, mime = gcs_uri(filename), MIME_TYPES[path.suffix.lower()]
    options = _process_options(chunk_size)
    try:
        raw, mode = _parse_online(client, name, uri, mime, options), "online"
    except InvalidArgument as exc:
        print(f"         online call rejected ({str(exc)[:140]}); switching to batch")
        raw, mode = _parse_batch(client, name, uri, mime, options, stem, chunk_size), "batch"

    cache.write_text(json.dumps({
        "meta": {
            "filename": filename, "md5": md5, "mode": mode,
            "processor_version": PROCESSOR_VERSION, "chunk_size": chunk_size,
            "include_ancestor_headings": INCLUDE_ANCESTOR_HEADINGS,
            "table_annotation": ENABLE_TABLE_ANNOTATION, "image_annotation": ENABLE_IMAGE_ANNOTATION,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
        },
        "document": raw,
    }, ensure_ascii=False), encoding="utf-8")
    return raw, mode


def main() -> None:
    """Parse every allowlisted file (or one) and write the chunk list."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--file", help="parse only this file name")
    args = parser.parse_args()

    files = [args.file] if args.file else SOURCE_FILES
    unknown = set(files) - set(SOURCE_FILES)
    if unknown:
        raise SystemExit(f"Not in the SOURCE_FILES allowlist: {sorted(unknown)}")

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    doc_ids = _document_ids()
    client = _client()
    name = _processor_version_name(client)

    all_rows = []
    for filename in files:
        print(f"[parse] {filename} (chunk_size={args.chunk_size})")
        raw, mode = parse_file(client, name, filename, args.chunk_size)
        rows = _chunk_rows(doc_ids[filename], filename, args.chunk_size, raw)
        all_rows.extend(rows)
        pages = max((r["page_end"] or 0 for r in rows), default=0)
        print(f"         {mode:6}  {len(rows):4} chunks  pages 1–{pages}")

    out = OUTPUT_DIR / f"chunks_cs{args.chunk_size}.json"
    if args.file and out.exists():
        # Single-file run: replace only that file's chunks in the existing list.
        kept = [r for r in json.loads(out.read_text(encoding="utf-8")) if r["filename"] != args.file]
        all_rows = kept + all_rows
    out.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(all_rows)} chunks to {out.relative_to(OUTPUT_DIR.parent)}")


if __name__ == "__main__":
    main()
