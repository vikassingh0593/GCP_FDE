"""Turn the runbook and postmortem PDFs into the searchable doc_chunks table.

Run from retail-control-tower/, after `python -m scripts.load_data`:

    python -m scripts.ingest_docs                                  # ingest into doc_chunks
    python -m scripts.ingest_docs --dry-run                        # show the plan; no cloud calls
    python -m scripts.ingest_docs --chunk-size 256                 # Gate 2 experiment -> doc_chunks_cs256_d768
    python -m scripts.ingest_docs --dimension 3072                 # Gate 3 experiment -> doc_chunks_cs512_d3072
    python -m scripts.ingest_docs --reparse                        # ignore the Document AI result cache

Steps:
  1. Options      - chunk size, dimension and target table. A non-default chunk
                    size or dimension writes to its own experiment table, so an
                    experiment never overwrites doc_chunks.
  2. Register     - read document_register from BigQuery (loaded by load_data).
                    It is the work list (only registered documents are ingested)
                    and the source of every chunk's labels (doc_id, version,
                    status, type, dates). Metadata never comes from the PDF.
  3. Bucket       - every registered PDF is in the bucket, non-empty and a PDF.
                    Its MD5 and generation are kept: the parse cache key (step 5)
                    and the provenance of every chunk (step 7).
  4. Processor    - the Document AI Layout Parser processor exists, is enabled,
                    and the pinned version is still offered (session 8
                    00_provision, plus a stale-ID check and a version check).
  5. Parse        - Layout Parser reads each PDF from the bucket (OCR for the
                    scan) and chunks it, with ancestor headings. The raw result
                    is cached under output/parsed/, keyed by the file's MD5 and
                    the parse settings (session 8 02_parse).
  6. Quality gate - stop before paying for embeddings if parsing failed: every
                    document has chunks, enough text, and its own ID in the text
                    (proves OCR worked on the scan).
  7. Rows         - one row per SECTION, labelled from the register, with the
                    section path, pages, source MD5 and an index version.
                    chunk_size is only a maximum for Layout Parser: it packs a
                    whole short runbook into one chunk. So each parser chunk is
                    split again at its "##" headings, and every piece keeps the
                    document title (Gate 2: one procedure or section per chunk).
                    --no-section-split keeps the parser's chunks (Gate 2 experiment).
  8. Embed        - RETRIEVAL_DOCUMENT embeddings. Vectors are cached by text
                    hash + model + dimension, so an unchanged chunk is never
                    embedded twice.
  9. Save         - WRITE_TRUNCATE into the target table: one job that fully
                    succeeds or fully fails, so search never sees half an index.
 10. Verify       - row counts, every registered document is present, and probe
                    searches through the real search path: a paraphrase, an
                    exact code, the OCR document, and the superseded runbook
                    never coming back.

Status is stamped on each chunk as a snapshot; search must still check status
against document_register at question time, so a withdrawn document disappears
before it is re-ingested.

Not here: batch processing. Our PDFs are 1-3 pages, well inside the online
limit, so an online call is enough; a file Document AI rejects fails the run
with its name instead of switching mode silently.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import time
from datetime import date, datetime, timezone

from common import config
from common.utils import fail, log
from scripts.load_data import REGISTER_REQUIRED, REGISTER_STATUSES   # one definition of a valid register

LAYOUT_PARSER_TYPE = "LAYOUT_PARSER_PROCESSOR"
# Generated image/table descriptions are model text, not document text: we switch them off,
# and still strip the markers if a parser version adds them (session 8 D7).
ANNOTATION = re.compile(r"__START_OF_ANNOTATION__(.*?)__END_OF_ANNOTATION__", re.S)
MIN_DOC_CHARS = 200                     # less text than this = the parse failed (blank scan, wrong file)
DOC_EMBEDDING_CACHE_TTL_SECONDS = 90 * 24 * 3600

# Probe searches (step 10): (label, question, expected doc, expected version or None).
PROBES = [
    ("paraphrase", "Stock is sitting on the shelf but it is held for other customers' orders. What do we do?",
     "RB-ALLOC-002", "3"),
    ("exact code", "WX-HOLD", "RB-CAR-003", None),
    ("OCR (scanned PDF)", "risk rule update put repeat cash-on-delivery customers on credit hold",
     "PM-2025-052", None),
]
SUPERSEDED_PROBE = ("superseded never returned", "can the warehouse lead release reservations older than 24 hours",
                    "RB-ALLOC-002", "2")

CHUNKS_SCHEMA = [
    ("chunk_id", "STRING", "REQUIRED", "doc_id@vversion#cNNN"),
    ("doc_key", "STRING", "REQUIRED", "doc_id@vversion: search keeps only the register's current keys"),
    ("doc_id", "STRING", "REQUIRED", "From the register"),
    ("version", "STRING", "REQUIRED", "From the register"),
    ("status", "STRING", "REQUIRED", "Register status at ingest time (a snapshot: search joins the register)"),
    ("doc_type", "STRING", "REQUIRED", "runbook | postmortem"),
    ("title", "STRING", "REQUIRED", "From the register"),
    ("exception_type", "STRING", "NULLABLE", "From the register"),
    ("owner", "STRING", "NULLABLE", "From the register (runbooks)"),
    ("effective_date", "DATE", "NULLABLE", "From the register (runbooks)"),
    ("incident_date", "DATE", "NULLABLE", "From the register (postmortems)"),
    ("warehouse_id", "STRING", "NULLABLE", "From the register (postmortems)"),
    ("carrier", "STRING", "NULLABLE", "From the register (postmortems)"),
    ("region", "STRING", "NULLABLE", "From the register (postmortems)"),
    ("media", "STRING", "REQUIRED", "pdf_text | pdf_scan"),
    ("section", "STRING", "NULLABLE", "Heading path from Layout Parser's ancestor headings"),
    ("content", "STRING", "REQUIRED", "Chunk text (headings included)"),
    ("position", "INT64", "REQUIRED", "Chunk order in the document"),
    ("page_start", "INT64", "NULLABLE", ""),
    ("page_end", "INT64", "NULLABLE", ""),
    ("chunk_size", "INT64", "REQUIRED", "Layout Parser chunk size in tokens"),
    ("source_uri", "STRING", "REQUIRED", "gs:// path of the parsed PDF"),
    ("source_md5", "STRING", "REQUIRED", "MD5 (hex) of the parsed PDF"),
    ("source_generation", "INT64", "NULLABLE", "Cloud Storage generation of the parsed PDF"),
    ("processor_version", "STRING", "REQUIRED", "Document AI Layout Parser version"),
    ("embedding_model", "STRING", "REQUIRED", ""),
    ("embedding_dimension", "INT64", "REQUIRED", ""),
    ("embedding", "FLOAT64", "REPEATED", "RETRIEVAL_DOCUMENT vector"),
    ("index_version", "STRING", "REQUIRED", "Hash of documents + parse + embedding settings"),
    ("ingested_at", "TIMESTAMP", "REQUIRED", ""),
]


# -----------------------------------------------------------------------------
# 1. Options
# -----------------------------------------------------------------------------

def target_table(chunk_size: int, dimension: int, explicit: str | None) -> str:
    """doc_chunks for the configured settings; a separate experiment table otherwise."""
    if explicit:
        return explicit
    if chunk_size == config.CHUNK_SIZE and dimension == config.EMBEDDING_DIMENSION:
        return config.BQ_DOC_CHUNKS_TABLE
    return f"{config.BQ_DOC_CHUNKS_TABLE}_cs{chunk_size}_d{dimension}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse, chunk and embed the registered PDFs into BigQuery.")
    parser.add_argument("--dry-run", action="store_true", help="show the plan; no cloud calls")
    parser.add_argument("--chunk-size", type=int, default=config.CHUNK_SIZE,
                        help=f"Layout Parser chunk size in tokens (default {config.CHUNK_SIZE})")
    parser.add_argument("--dimension", type=int, default=config.EMBEDDING_DIMENSION,
                        choices=(768, 1536, 3072),
                        help=f"embedding dimension (default {config.EMBEDDING_DIMENSION})")
    parser.add_argument("--table", help="target table name (default: doc_chunks, or an experiment table)")
    parser.add_argument("--reparse", action="store_true", help="ignore cached Document AI results")
    parser.add_argument("--skip-probes", action="store_true", help="verify counts only (no search probes)")
    parser.add_argument("--no-section-split", action="store_true",
                        help="keep Layout Parser's chunks as they are (Gate 2 experiment; needs --table)")
    args = parser.parse_args(argv)
    if args.chunk_size <= 0:
        parser.error("--chunk-size must be positive")
    if args.no_section_split and not args.table:
        parser.error("--no-section-split is an experiment: give it its own --table (e.g. doc_chunks_whole)")
    args.table = target_table(args.chunk_size, args.dimension, args.table)
    return args


# -----------------------------------------------------------------------------
# 2. Register: from BigQuery, the work list and the labels
# -----------------------------------------------------------------------------

def read_register(bq) -> list[dict]:
    """All registered document versions (current and superseded), checked before anything is parsed.

    Superseded versions are ingested too: the index must know v2 exists, and
    search filters it out by status.
    """
    from google.api_core.exceptions import NotFound

    table = config.table_id(config.BQ_DOCUMENT_REGISTER_TABLE)
    try:
        rows = [dict(r.items()) for r in bq.query(
            f"SELECT * FROM `{table}` ORDER BY doc_type, doc_id, version").result()]
    except NotFound:
        fail(f"{table} not found. Run: python -m scripts.load_data")
    if not rows:
        fail(f"{table} is empty. Run: python -m scripts.load_data")

    problems = []
    for row in rows:
        label = f"{row.get('doc_id') or '?'} v{row.get('version') or '?'}"
        missing = [c for c in REGISTER_REQUIRED if not str(row.get(c) or "").strip()]
        if missing:
            problems.append(f"{label}: missing {', '.join(missing)}")
        if row.get("status") not in REGISTER_STATUSES:
            problems.append(f"{label}: status {row.get('status')!r} is not one of {sorted(REGISTER_STATUSES)}")
    keys = [(r.get("doc_id"), r.get("version")) for r in rows]
    if len(keys) != len(set(keys)):
        problems.append("duplicate (doc_id, version) rows")
    if problems:
        fail("document_register problems:\n  - " + "\n  - ".join(problems))

    log("ok", f"register: {len(rows)} documents "
              f"({sum(r['status'] == 'current' for r in rows)} current, "
              f"{sum(r['status'] == 'superseded' for r in rows)} superseded, "
              f"{sum(r['media'] == 'pdf_scan' for r in rows)} scanned) from {table}")
    return rows


def doc_key(row: dict) -> tuple[str, str]:
    return row["doc_id"], str(row["version"])


def label(row: dict) -> str:
    return f"{row['doc_id']} v{row['version']}"


def show(path) -> str:
    """Path relative to the project when it is inside it (shorter logs), absolute otherwise."""
    try:
        return str(path.relative_to(config.ROOT))
    except ValueError:
        return str(path)


# -----------------------------------------------------------------------------
# 3. Bucket: every registered PDF is there
# -----------------------------------------------------------------------------

def object_name(row: dict) -> str:
    """Same naming rule as load_data (config.gcs_doc_path); the local file doesn't need to exist."""
    return config.gcs_doc_path(config.DOCS_DIR / row["file_path"])


def md5_hex(md5_base64: str) -> str:
    """Cloud Storage reports MD5 in base64; the cache and the chunk rows use hex."""
    return base64.b64decode(md5_base64).hex()


def check_bucket(gcs, register: list[dict]) -> dict[tuple[str, str], dict]:
    """(doc_id, version) -> {object, uri, md5, generation} for every registered PDF.

    One list call for the whole prefix, not one exists() call per document.
    Objects in the bucket that the register doesn't list are skipped, never
    ingested: they have no metadata, so search couldn't filter them.
    """
    remote = {b.name: b for b in gcs.list_blobs(config.GCS_BUCKET, prefix=f"{config.GCS_DOCS_PREFIX}/")}
    sources, problems = {}, []
    for row in register:
        name = object_name(row)
        blob = remote.get(name)
        if blob is None:
            problems.append(f"{label(row)}: {config.gcs_uri(name)} is not in the bucket")
            continue
        if not blob.size:
            problems.append(f"{label(row)}: {config.gcs_uri(name)} is empty")
            continue
        if blob.content_type != "application/pdf":
            problems.append(f"{label(row)}: {config.gcs_uri(name)} has content type {blob.content_type!r}, "
                            "expected application/pdf")
            continue
        sources[doc_key(row)] = {"object": name, "uri": config.gcs_uri(name),
                                 "md5": md5_hex(blob.md5_hash), "generation": blob.generation}
    if problems:
        fail("bucket problems:\n  - " + "\n  - ".join(problems) + "\nRun: python -m scripts.load_data")

    registered = {object_name(r) for r in register}
    extra = sorted(n for n in remote if n not in registered and not n.endswith("/"))
    for name in extra:
        log("skip", f"{config.gcs_uri(name)} is not in the register; not ingested")
    log("ok", f"bucket: {len(sources)} registered PDFs present ({len(extra)} unregistered objects skipped)")
    return sources


# -----------------------------------------------------------------------------
# 4. Processor: Layout Parser exists, is enabled, and the pinned version is offered
# -----------------------------------------------------------------------------

def docai_client():
    """Document AI is regional, so the client must call the regional endpoint."""
    from google.cloud import documentai
    return documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{config.DOCUMENT_AI_LOCATION}-documentai.googleapis.com"})


def _check_processor(processor) -> None:
    from google.cloud import documentai
    if processor.type_ != LAYOUT_PARSER_TYPE:
        fail(f"processor {processor.name} is a {processor.type_}, not a {LAYOUT_PARSER_TYPE}. "
             f"Set DOCUMENT_AI_PROCESSOR_NAME to a new name in lab.env.")
    if processor.state != documentai.Processor.State.ENABLED:
        fail(f"processor {processor.name} is {processor.state.name}, not ENABLED. Enable it in the console.")


def ensure_processor(client) -> str:
    """Full resource name of the pinned processor version, after checking it is usable.

    Session 8 trusted the saved ID file. If the processor was deleted (or the
    project changed), that stale ID only failed later, inside the parse calls,
    with a confusing NotFound. Here the saved ID is checked first; a stale one
    falls through to find-by-name, then create.
    """
    from google.api_core.exceptions import NotFound
    from google.cloud import documentai

    parent = client.common_location_path(config.PROJECT_ID, config.DOCUMENT_AI_LOCATION)
    id_file = config.DOCUMENT_AI_PROCESSOR_ID_FILE
    id_file.parent.mkdir(parents=True, exist_ok=True)
    processor = None

    if id_file.exists():
        saved = id_file.read_text(encoding="utf-8").strip()
        try:
            processor = client.get_processor(name=client.processor_path(
                config.PROJECT_ID, config.DOCUMENT_AI_LOCATION, saved))
            log("reuse", f"Document AI processor {saved}")
        except NotFound:
            log("warn", f"saved processor ID {saved} no longer exists; looking it up by name")

    if processor is None:
        for existing in client.list_processors(parent=parent):
            if existing.display_name == config.DOCUMENT_AI_PROCESSOR_NAME:
                processor = existing
                log("found", f"Document AI processor {existing.name.rsplit('/', 1)[-1]} "
                             f"({config.DOCUMENT_AI_PROCESSOR_NAME})")
                break

    if processor is None:
        processor = client.create_processor(parent=parent, processor=documentai.Processor(
            display_name=config.DOCUMENT_AI_PROCESSOR_NAME, type_=LAYOUT_PARSER_TYPE))
        log("create", f"Document AI processor {processor.name.rsplit('/', 1)[-1]} "
                      f"({config.DOCUMENT_AI_PROCESSOR_NAME})")

    _check_processor(processor)
    processor_id = processor.name.rsplit("/", 1)[-1]
    id_file.write_text(processor_id, encoding="utf-8")

    # Models and parser versions retire. Check the pinned one now, not after 13 failed parses.
    version_name = client.processor_version_path(config.PROJECT_ID, config.DOCUMENT_AI_LOCATION,
                                                 processor_id, config.DOCUMENT_AI_PROCESSOR_VERSION)
    try:
        client.get_processor_version(name=version_name)
    except NotFound:
        offered = sorted(v.name.rsplit("/", 1)[-1] for v in client.list_processor_versions(parent=processor.name))
        fail(f"Layout Parser version {config.DOCUMENT_AI_PROCESSOR_VERSION} is not offered any more.\n"
             f"  Offered: {', '.join(offered) or 'none'}\n"
             f"  Set DOCUMENT_AI_PROCESSOR_VERSION in lab.env to one of them.")
    log("ok", f"processor version {config.DOCUMENT_AI_PROCESSOR_VERSION}")
    return version_name


# -----------------------------------------------------------------------------
# 5. Parse: Layout Parser, cached by file MD5 + parse settings
# -----------------------------------------------------------------------------

def process_options(chunk_size: int):
    from google.cloud import documentai
    return documentai.ProcessOptions(
        layout_config=documentai.ProcessOptions.LayoutConfig(
            enable_table_annotation=False,
            enable_image_annotation=False,
            chunking_config=documentai.ProcessOptions.LayoutConfig.ChunkingConfig(
                chunk_size=chunk_size,
                include_ancestor_headings=config.INCLUDE_ANCESTOR_HEADINGS,
            ),
        )
    )


def cache_path(row: dict, source: dict, chunk_size: int):
    settings = f"{config.DOCUMENT_AI_PROCESSOR_VERSION}|{config.INCLUDE_ANCESTOR_HEADINGS}"
    settings_hash = hashlib.sha256(settings.encode()).hexdigest()[:6]
    return config.PARSED_DIR / (f"{row['doc_id']}_v{row['version']}__cs{chunk_size}__{settings_hash}"
                                f"__{source['md5'][:12]}.json")


def parse_online(client, version_name: str, uri: str, chunk_size: int) -> dict:
    from google.cloud import documentai
    request = documentai.ProcessRequest(
        name=version_name,
        gcs_document=documentai.GcsDocument(gcs_uri=uri, mime_type="application/pdf"),
        process_options=process_options(chunk_size),
    )
    document = client.process_document(request=request, timeout=120).document
    return json.loads(documentai.Document.to_json(document))


def parse_all(client, version_name: str, register: list[dict], sources: dict, chunk_size: int,
              reparse: bool) -> dict[tuple[str, str], dict]:
    from google.api_core.exceptions import InvalidArgument
    from common.clients import with_retry

    config.PARSED_DIR.mkdir(parents=True, exist_ok=True)
    parsed = {}
    for row in register:
        source = sources[doc_key(row)]
        path = cache_path(row, source, chunk_size)
        if path.exists() and not reparse:
            parsed[doc_key(row)] = json.loads(path.read_text(encoding="utf-8"))["document"]
            log("cache", f"{label(row):18} parse reused ({path.name})")
            continue
        started = time.monotonic()
        try:
            raw = with_retry(lambda: parse_online(client, version_name, source["uri"], chunk_size),
                             f"parse {row['doc_id']}")
        except InvalidArgument as exc:
            fail(f"Document AI rejected {label(row)} ({source['uri']}): {str(exc)[:200]}")
        path.write_text(json.dumps({
            "meta": {"doc_id": row["doc_id"], "version": str(row["version"]), "uri": source["uri"],
                     "md5": source["md5"], "processor_version": config.DOCUMENT_AI_PROCESSOR_VERSION,
                     "chunk_size": chunk_size, "include_ancestor_headings": config.INCLUDE_ANCESTOR_HEADINGS,
                     "parsed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            "document": raw,
        }, ensure_ascii=False), encoding="utf-8")
        parsed[doc_key(row)] = raw
        chunks = len(raw.get("chunkedDocument", {}).get("chunks", []))
        log("parse", f"{label(row):18} {chunks:3} chunks in {time.monotonic() - started:.1f}s"
                     f"{'  (OCR)' if row['media'] == 'pdf_scan' else ''}")
    return parsed


# -----------------------------------------------------------------------------
# 6. Quality gate: before any embedding is paid for
# -----------------------------------------------------------------------------

def chunk_texts(raw: dict) -> list[str]:
    return [ANNOTATION.sub("", c.get("content", "")).strip()
            for c in raw.get("chunkedDocument", {}).get("chunks", [])]


def quality_gate(register: list[dict], parsed: dict) -> None:
    """Every document has chunks, enough text, and its own ID in the text.

    The ID check is the one that matters for the scan: a blank OCR result has
    no "PM-2025-052" in it, and a wrong file has someone else's ID.
    """
    problems = []
    for row in register:
        texts = [t for t in chunk_texts(parsed[doc_key(row)]) if t]
        joined = " ".join(texts)
        if not texts:
            problems.append(f"{label(row)}: no chunks")
        elif len(joined) < MIN_DOC_CHARS:
            problems.append(f"{label(row)}: only {len(joined)} characters of text")
        elif row["doc_id"] not in joined:
            problems.append(f"{label(row)}: its document ID is not in the parsed text"
                            f"{' (OCR may have failed)' if row['media'] == 'pdf_scan' else ''}")
    if problems:
        fail("parse quality gate failed (nothing was embedded or written):\n  - " + "\n  - ".join(problems))
    log("ok", f"quality gate: {len(register)} documents parsed with text and their own ID")


# -----------------------------------------------------------------------------
# 7. Rows: labelled from the register
# -----------------------------------------------------------------------------

def split_headings(text: str) -> tuple[str | None, str]:
    """Layout Parser puts the ancestor headings first, as markdown '#' lines (session 8 _is_heading)."""
    headings = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            headings.append(line.lstrip("#").strip())
        elif line.strip():
            break
    return (" > ".join(h for h in headings if h) or None), text


def split_sections(text: str) -> list[str]:
    """One piece per "##" section. Each piece starts with the "#" title line, so it reads on its own.

    Text before the first "##" (a summary under the title) is kept as its own piece;
    a piece that is only headings is dropped.
    """
    lines = text.splitlines()
    title = next((l.strip() for l in lines if l.lstrip().startswith("# ")), None)
    pieces, current = [], []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("# "):
            continue                                    # the title goes on every piece instead
        if stripped.startswith("## ") and current:
            pieces.append(current)
            current = []
        current.append(line)
    if current:
        pieces.append(current)
    out = []
    for piece in pieces:
        body = [l for l in piece if l.strip() and not l.lstrip().startswith("#")]
        if not body:
            continue
        out.append("\n".join(([title, ""] if title else []) + piece).strip())
    return out or [text]


def _date(value) -> str | None:
    if value in (None, ""):
        return None
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


def index_version(register: list[dict], sources: dict, chunk_size: int, dimension: int) -> str:
    parts = sorted(f"{r['doc_id']}|{r['version']}|{r['status']}|{sources[doc_key(r)]['md5']}" for r in register)
    parts += [f"cs={chunk_size}", f"pv={config.DOCUMENT_AI_PROCESSOR_VERSION}",
              f"ah={config.INCLUDE_ANCESTOR_HEADINGS}", f"em={config.EMBEDDING_MODEL}@{dimension}"]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:12]


def build_rows(register: list[dict], sources: dict, parsed: dict, chunk_size: int, dimension: int,
               section_split: bool = True) -> list[dict]:
    version = index_version(register, sources, chunk_size, dimension)
    if not section_split:
        version = hashlib.sha256(f"{version}|whole".encode()).hexdigest()[:12]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for reg in register:
        source = sources[doc_key(reg)]
        labels = {
            "doc_key": f"{reg['doc_id']}@v{reg['version']}",
            "doc_id": reg["doc_id"], "version": str(reg["version"]), "status": reg["status"],
            "doc_type": reg["doc_type"], "title": reg["title"],
            "exception_type": reg.get("exception_type") or None, "owner": reg.get("owner") or None,
            "effective_date": _date(reg.get("effective_date")), "incident_date": _date(reg.get("incident_date")),
            "warehouse_id": reg.get("warehouse_id") or None, "carrier": reg.get("carrier") or None,
            "region": reg.get("region") or None, "media": reg["media"],
        }
        position = 0
        for chunk in parsed[doc_key(reg)].get("chunkedDocument", {}).get("chunks", []):
            content = ANNOTATION.sub("", chunk.get("content", "")).strip()
            if not content:
                continue
            span = chunk.get("pageSpan", {})
            for piece in (split_sections(content) if section_split else [content]):
                section, text = split_headings(piece)
                rows.append({
                    "chunk_id": f"{labels['doc_key']}#c{position:03d}", **labels,
                    "section": section, "content": text, "position": position,
                    "page_start": span.get("pageStart"), "page_end": span.get("pageEnd"),
                    "chunk_size": chunk_size, "source_uri": source["uri"], "source_md5": source["md5"],
                    "source_generation": source["generation"],
                    "processor_version": config.DOCUMENT_AI_PROCESSOR_VERSION,
                    "embedding_model": config.EMBEDDING_MODEL, "embedding_dimension": dimension,
                    "index_version": version, "ingested_at": now,
                })
                position += 1
    log("ok", f"{len(rows)} chunk rows from {len(register)} documents "
              f"({'one per section' if section_split else 'parser chunks as they are'}), index version {version}")
    return rows


# -----------------------------------------------------------------------------
# 8. Embed: RETRIEVAL_DOCUMENT, cached by text hash + model + dimension
# -----------------------------------------------------------------------------

def embedding_text(row: dict) -> str:
    return f"{row['title']} ({row['doc_id']} v{row['version']})\n{row['section'] or ''}\n{row['content']}"


def embed_rows(rows: list[dict], dimension: int) -> dict:
    from orchestrator.retrieval.cache import TTLCache
    from orchestrator.retrieval.embeddings import embed_document

    cache = TTLCache(f"doc_embeddings_d{dimension}", DOC_EMBEDDING_CACHE_TTL_SECONDS)
    started = time.monotonic()
    for row in rows:
        text = embedding_text(row)
        key = TTLCache.key(hashlib.sha256(text.encode()).hexdigest(), config.EMBEDDING_MODEL, dimension)
        vector = cache.get(key)
        if vector is None:
            vector = embed_document(text, title=row["title"], dimension=dimension)
            cache.put(key, vector)
        if len(vector) != dimension:
            fail(f"{row['chunk_id']}: embedding has {len(vector)} values, expected {dimension}")
        row["embedding"] = vector
    stats = cache.stats()
    log("ok", f"embedded {len(rows)} chunks ({stats['misses']} new, {stats['hits']} from cache) "
              f"in {time.monotonic() - started:.1f}s")
    return stats


# -----------------------------------------------------------------------------
# 9. Save: WRITE_TRUNCATE
# -----------------------------------------------------------------------------

def save_rows(bq, rows: list[dict], table: str) -> None:
    from google.cloud import bigquery

    schema = [bigquery.SchemaField(n, t, mode=m, description=d) for n, t, m, d in CHUNKS_SCHEMA]
    job = bq.load_table_from_json(rows, config.table_id(table), job_config=bigquery.LoadJobConfig(
        schema=schema, write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        destination_table_description="Runbook and postmortem chunks with embeddings (scripts/ingest_docs.py). "
                                      "Search joins document_register for status at question time."))
    job.result()
    log("load", f"{config.table_id(table)}: {job.output_rows} rows (job {job.job_id})")


# -----------------------------------------------------------------------------
# 10. Verify: counts + probes through the real search path
# -----------------------------------------------------------------------------

def verify(bq, rows: list[dict], register: list[dict], table: str, dimension: int, run_probes: bool) -> dict:
    problems = []
    count = bq.get_table(config.table_id(table)).num_rows
    log("ok" if count == len(rows) else "FAIL", f"{table}: {count} rows (wrote {len(rows)})")
    if count != len(rows):
        problems.append(f"{table} has {count} rows, expected {len(rows)}")
    present = {(r["doc_id"], r["version"]) for r in rows}
    missing = [label(r) for r in register if doc_key(r) not in present]
    if missing:
        problems.append(f"no chunks for: {', '.join(missing)}")
    else:
        log("ok", f"every registered document has chunks ({len(register)})")

    probes = []
    if run_probes:
        from orchestrator.retrieval.search import search

        for name, question, doc, version in PROBES:
            out = search(question, table=table, dimension=dimension, use_cache=False)
            docs = out.get("_trace", {}).get("docs", [])
            hit = next((i for i, d in enumerate(docs, start=1)
                        if d.split("@")[0] == doc and (version is None or d.endswith(f"@v{version}"))), None)
            probes.append({"probe": name, "question": question, "expected": doc, "rank": hit, "docs": docs})
            log("ok" if hit else "FAIL", f"probe {name:18} -> {doc} at rank {hit or '-'}  {docs}")
            if not hit:
                problems.append(f"probe '{name}' did not return {doc} in the top {config.TOP_N}")
        name, question, doc, version = SUPERSEDED_PROBE
        docs = search(question, table=table, dimension=dimension, use_cache=False).get("_trace", {}).get("docs", [])
        leaked = f"{doc}@v{version}" in docs
        probes.append({"probe": name, "question": question, "forbidden": f"{doc}@v{version}", "docs": docs})
        log("FAIL" if leaked else "ok", f"probe {name:18} -> {doc} v{version} {'RETURNED' if leaked else 'not returned'}")
        if leaked:
            problems.append(f"superseded {doc} v{version} came back from search")

    if problems:
        fail("verification found problems:\n  - " + "\n  - ".join(problems))
    return {"rows": count, "probes": probes}


# -----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    started = time.monotonic()
    print(f"project {config.PROJECT_ID} | register {config.table_id(config.BQ_DOCUMENT_REGISTER_TABLE)}\n"
          f"target {config.table_id(args.table)} | chunk size {args.chunk_size} | "
          f"{config.EMBEDDING_MODEL}@{args.dimension}\n"
          f"Document AI {config.DOCUMENT_AI_PROCESSOR_NAME} ({config.DOCUMENT_AI_LOCATION}, "
          f"{config.DOCUMENT_AI_PROCESSOR_VERSION})\n")

    if args.dry_run:
        log("plan", f"read the register from {config.table_id(config.BQ_DOCUMENT_REGISTER_TABLE)}")
        log("plan", f"check every registered PDF is in gs://{config.GCS_BUCKET}/{config.GCS_DOCS_PREFIX}/")
        log("plan", f"ensure processor {config.DOCUMENT_AI_PROCESSOR_NAME} and version "
                    f"{config.DOCUMENT_AI_PROCESSOR_VERSION}")
        log("plan", f"parse each PDF (cache: {show(config.PARSED_DIR)}/), quality gate, "
                    f"embed, write {config.table_id(args.table)} (WRITE_TRUNCATE), probe searches")
        print("\nDry run: nothing was sent to the cloud.")
        return

    from google.cloud import bigquery, storage

    bq = bigquery.Client(project=config.PROJECT_ID, location=config.BIGQUERY_LOCATION)
    gcs = storage.Client(project=config.PROJECT_ID)

    log("step", "2. register")
    register = read_register(bq)

    log("step", "3. bucket")
    sources = check_bucket(gcs, register)

    log("step", "4. processor")
    client = docai_client()
    version_name = ensure_processor(client)

    log("step", "5. parse")
    parsed = parse_all(client, version_name, register, sources, args.chunk_size, args.reparse)

    log("step", "6. quality gate")
    quality_gate(register, parsed)

    log("step", "7. rows")
    rows = build_rows(register, sources, parsed, args.chunk_size, args.dimension,
                      section_split=not args.no_section_split)

    log("step", "8. embed")
    embed_stats = embed_rows(rows, args.dimension)

    log("step", "9. save")
    save_rows(bq, rows, args.table)

    log("step", "10. verify")
    result = verify(bq, rows, register, args.table, args.dimension, run_probes=not args.skip_probes)

    report = {"table": args.table, "chunk_size": args.chunk_size, "dimension": args.dimension,
              "index_version": rows[0]["index_version"], "documents": len(register), "chunks": len(rows),
              "embeddings": embed_stats, "seconds": round(time.monotonic() - started, 1), **result}
    report_path = config.OUTPUT_DIR / f"ingest_{args.table}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nINGEST COMPLETE in {report['seconds']}s: {len(rows)} chunks from {len(register)} documents "
          f"-> {config.table_id(args.table)}. Report: {show(report_path)}")


if __name__ == "__main__":
    main()
