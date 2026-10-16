"""Turn the checked chunks into the searchable BigQuery `chunks` table (Step 2.4).

Input: output/chunks_cs<CHUNK_SIZE>.json (02_parse.py), output/quarantine.json
and output/parse_report.json (02a_check_parse.py), the cached raw parses in
output/parsed/, and the BigQuery `documents` table.

In order:
 a. skip quarantined files
 b. split every Markdown table out into its own chunk; its page comes from the
    table block, not the chunk span (decisions D11, D18)
 c. drop barcode/QR descriptions; chart descriptions become separate figure
    chunks tagged generated = true (D13)
 d. tag template text as boilerplate: sentences whose number-masked form appears
    5+ times in the corpus; a chunk >= 90 % template is excluded from search
 e. collapse exact copies within a document, recording the other places (also_in)
 f. flag table chunks whose text differs from the PDF (faithfulness) needs_review (D12, D17)
 g. add a "document card" for any document left with no searchable chunk (D20)
 h. copy governance fields from `documents`; embed (context prefix of title,
    version, country; status left out, D19); reuse stored vectors for unchanged
    text (D22); MERGE into `chunks` and delete stale rows of re-processed
    documents (D23); then the verify-searchable probe.

Every count and check is recorded in BigQuery `pipeline_health`.
Safe to re-run: a second run embeds nothing new and leaves the same rows.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from google import genai
from google.cloud import bigquery
from google.genai import types

from config import (
    BQ_CHUNKS_TABLE,
    BQ_DOCUMENTS_TABLE,
    CHUNK_SIZE,
    EMBEDDING_DIMENSION,
    EMBEDDING_LOCATION,
    EMBEDDING_MODEL,
    OUTPUT_DIR,
    PROCESSOR_VERSION,
    PROJECT_ID,
    table_id,
)
from health import Health


EMBEDDING_MODEL_TAG = f"{EMBEDDING_MODEL}@{EMBEDDING_DIMENSION}"
STAGING_TABLE = "_chunks_staging"

TEMPLATE_MIN_REPEATS = 5      # a sentence shape seen this often is template text
BOILERPLATE_SHARE = 0.9       # a chunk this template-heavy is excluded from search
EMBED_WORKERS = 4

# One probe per document: a phrase the bot must be able to find (Step 9 design).
PROBES = {
    "DE-AX17-LBL-042": "Table 3 renal dose modification moderate renal impairment Germany",
    "DE-AX17-LBL-038": "historical renal dosing superseded German label",
    "US-AX17-PI-050": "US renal recommendations moderate renal impairment",
    "HN-204": "HN-204 treatment-emergent adverse events table",
    "HN-311": "HN-311 treatment-emergent adverse events table",
    "HN-402": "HN-402 treatment-emergent adverse events table",
    "SB-AX17-2026-09": "repeat testing between Day 14 and Day 21 hepatic monitoring",
    "DE-AX17-HSL-2019-2021": "historical AX-17 safety letters Germany 2019 2021 archive",
}


# -----------------------------------------------------------------------------
# Inputs
# -----------------------------------------------------------------------------

def load_inputs():
    """Chunks, quarantine list, faithfulness flags and per-file extraction mode."""
    chunks = json.loads((OUTPUT_DIR / f"chunks_cs{CHUNK_SIZE}.json").read_text(encoding="utf-8"))
    quarantine = set(json.loads((OUTPUT_DIR / "quarantine.json").read_text(encoding="utf-8")))
    report = json.loads((OUTPUT_DIR / "parse_report.json").read_text(encoding="utf-8"))[str(CHUNK_SIZE)]
    review = {c for r in report for c in r.get("faithfulness", {}).get("table_chunks_to_review", [])}
    extraction = {r["filename"]: ("ocr" if r.get("ocr_pages") else "native") for r in report}
    return chunks, quarantine, review, extraction


def _cell_text(cell: dict) -> str:
    """Text inside one table cell (cells hold nested text blocks)."""
    parts = []
    for b in cell.get("blocks", []):
        if "textBlock" in b:
            parts.append(b["textBlock"].get("text", ""))
            parts.extend(_cell_text({"blocks": b["textBlock"].get("blocks", [])}).split("\n"))
    return " ".join(x.strip() for x in parts if x.strip())


def _header_key(cells: list[str]) -> str:
    """Header row as a lookup key, e.g. 'adverse event | ax-17 % | control % | serious?'."""
    return " | ".join(re.sub(r"\s+", " ", c).strip().lower() for c in cells)


def table_pages(filename: str) -> dict:
    """Table caption or header row (lower case) → page, from the raw parse's table blocks.

    Some table blocks have no caption (HN-204), so the header row is the
    fallback key; every table block has one.
    """
    stem = filename.rsplit(".", 1)[0]
    files = sorted(glob.glob(str(OUTPUT_DIR / "parsed" / f"{stem}__cs{CHUNK_SIZE}__*.json")), key=os.path.getmtime)
    if not files:
        return {}
    raw = json.loads(open(files[-1], encoding="utf-8").read())["document"]
    pages: dict = {}

    def walk(blocks):
        for b in blocks:
            if "tableBlock" in b and b.get("pageSpan"):
                page = b["pageSpan"].get("pageStart")
                caption = (b["tableBlock"].get("caption") or "").strip().lower()
                if caption:
                    pages[caption] = page
                header_rows = b["tableBlock"].get("headerRows") or []
                if header_rows:
                    pages[_header_key([_cell_text(c) for c in header_rows[0].get("cells", [])])] = page
            for kind in ("textBlock", "listBlock"):
                if kind in b:
                    walk(b[kind].get("blocks", []))

    walk(raw.get("documentLayout", {}).get("blocks", []))
    return pages


def documents_by_id(client: bigquery.Client) -> dict:
    """Governance fields from the registry table (source of truth)."""
    rows = client.query(f"""
        SELECT document_id, title, product, countries, status, raw_status, version,
               effective_from, valid_to, authority, document_type, view_url, gcs_uri
        FROM `{table_id(BQ_DOCUMENTS_TABLE)}`
    """).result()
    return {r.document_id: dict(r.items()) for r in rows}


# -----------------------------------------------------------------------------
# a–c: split tables out, separate figure descriptions
# -----------------------------------------------------------------------------

def _is_heading(line: str) -> bool:
    return line.lstrip().startswith("#")


def _heading_text(line: str) -> str:
    return line.lstrip("#").strip()


def split_chunk(chunk: dict, pages: dict) -> list[dict]:
    """One Layout Parser chunk → text / table / figure pieces."""
    lines = chunk["content"].splitlines()
    leading = []
    for line in lines:
        if not line.strip():
            continue
        if _is_heading(line):
            leading.append(_heading_text(line))
            continue
        break

    used = set()
    pieces = []
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("|"):
            i += 1
            continue
        start = i
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            i += 1
        end = i  # exclusive

        # Title: the nearest heading line just above the table.
        title_idx = next((j for j in range(start - 1, -1, -1) if lines[j].strip()), None)
        title_idx = title_idx if title_idx is not None and _is_heading(lines[title_idx]) else None
        title = _heading_text(lines[title_idx]) if title_idx is not None else ""
        # Caption: a short line right below the table, usually repeating the title.
        cap_idx = next((j for j in range(end, len(lines)) if lines[j].strip()), None)
        if cap_idx is not None and (_is_heading(lines[cap_idx]) or len(lines[cap_idx]) > 120
                                    or (title and lines[cap_idx].strip().lower() != title.lower()
                                        and not lines[cap_idx].strip().lower().startswith(("table", "figure")))):
            cap_idx = None

        caption = lines[cap_idx].strip() if cap_idx is not None else ""
        if not title and caption:
            title = caption  # e.g. HN-311: "Table 14. ..." printed below the table
        # Header = first row that is not a separator (DOCX tables start with "|-|-|").
        header_line = next(l for l in lines[start:end] if not re.fullmatch(r"\|?[\s:|-]+\|?", l.strip()))
        header_cells = [c.strip() for c in header_line.strip().strip("|").split("|")]

        idxs = [k for k in (title_idx, cap_idx) if k is not None] + list(range(start, end))
        used.update(idxs)
        context = [h for h in leading if h.lower() != title.lower()]
        body = "\n".join(lines[start:end])
        text = "\n\n".join(filter(None, ["# " + " › ".join(context) if context else "",
                                          f"# {title}" if title else "", body]))
        page = pages.get(title.lower()) or pages.get(caption.lower()) or pages.get(_header_key(header_cells))
        match = re.search(r"\bTable \d+\b", title)
        pieces.append({
            "block_type": "table",
            "content": text,
            "section_path": " › ".join(leading) or None,
            # e.g. "Table 3"; a caption-less table is named by its header row (bulletin).
            "table_id": match.group(0) if match else (title or " / ".join(header_cells)),
            "page_start": page or chunk["page_start"],
            "page_end": page or chunk["page_end"],
        })

    remainder = "\n".join(l for k, l in enumerate(lines) if k not in used).strip()
    if remainder and not all(_is_heading(l) for l in remainder.splitlines() if l.strip()):
        pieces.insert(0, {
            "block_type": "text",
            "content": remainder,
            "section_path": " › ".join(leading) or None,
            "table_id": None,
            "page_start": chunk["page_start"],
            "page_end": chunk["page_end"],
        })

    # Figure descriptions: keep charts (tagged generated), drop barcode/QR noise.
    dropped = 0
    has_table = any(p["block_type"] == "table" for p in pieces)
    for n, annotation in enumerate(chunk.get("annotations", []), start=1):
        head = annotation[:300].lower()
        if "barcode" in head or "qr code" in head:
            dropped += 1
            continue
        # The figure's own title, if the description quotes it; never the table's heading.
        titled = re.search(r'titled\s+["\u201c]([^"\u201d]+)["\u201d]', annotation[:400])
        caption = (titled.group(1).strip(" ,.;:") if titled else
                   (leading[-1] if leading and not has_table else f"Figure, p.{chunk['page_start']}"))
        pieces.append({
            "block_type": "figure",
            "content": f"# {caption}\n\n" + "Figure description (generated by the parser, "
                       "not document text):\n" + annotation,
            "section_path": " › ".join(leading) or None,
            "table_id": None,
            "figure_id": caption,
            "generated": True,
            "page_start": chunk["page_start"],
            "page_end": chunk["page_start"],
        })

    for k, piece in enumerate(pieces):
        suffix = {"text": "x", "table": "t", "figure": "f"}[piece["block_type"]]
        piece["chunk_id"] = chunk["chunk_id"] if len(pieces) == 1 else f"{chunk['chunk_id']}-{suffix}{k}"
        piece["position"] = chunk["position"] * 10 + k
        piece["source_chunk_id"] = chunk["chunk_id"]
        piece.setdefault("figure_id", None)
        piece.setdefault("generated", False)
    return pieces, dropped


# -----------------------------------------------------------------------------
# d–e: templates and exact copies
# -----------------------------------------------------------------------------

def _sentences(text: str) -> list[str]:
    body = " ".join(l for l in text.splitlines() if l.strip() and not _is_heading(l) and not l.lstrip().startswith("|"))
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]


def _shape(sentence: str) -> str:
    """A sentence with every number masked: the template paragraphs share one shape."""
    return re.sub(r"\d+(\.\d+)?", "#", sentence.lower())


def tag_templates(pieces: list[dict]) -> None:
    """Set template_share and boilerplate on every text piece."""
    counts = Counter(_shape(s) for p in pieces if p["block_type"] == "text" for s in _sentences(p["content"]))
    for p in pieces:
        if p["block_type"] != "text":
            p["template_share"], p["boilerplate"] = 0.0, False
            continue
        sentences = _sentences(p["content"])
        total = sum(len(s) for s in sentences) or 1
        share = sum(len(s) for s in sentences if counts[_shape(s)] >= TEMPLATE_MIN_REPEATS) / total
        p["template_share"] = round(share, 3)
        p["boilerplate"] = share >= BOILERPLATE_SHARE


def _norm_hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text.lower()).strip().encode()).hexdigest()


def collapse_copies(pieces: list[dict]) -> tuple[list[dict], int]:
    """Keep the first of identical pieces within a document; record where the others were."""
    kept, first = [], {}
    collapsed = 0
    for p in pieces:
        # Compare without heading lines: the bulletin's 3 table copies differ only
        # in their section heading ("4. ...", "9. ...", "14. ...").
        body = "\n".join(l for l in p["content"].splitlines() if not _is_heading(l))
        p["content_hash"] = _norm_hash(body)
        key = (p["document_id"], p["content_hash"])
        if key in first:
            where = f"{p['chunk_id']}" + (f" (p.{p['page_start']})" if p["page_start"] else "")
            first[key]["also_in"].append(where)
            collapsed += 1
            continue
        p["also_in"] = []
        first[key] = p
        kept.append(p)
    return kept, collapsed


# -----------------------------------------------------------------------------
# g: document card
# -----------------------------------------------------------------------------

def document_card(doc: dict, chunks: list[dict], extraction: str) -> dict:
    """A searchable summary for a document whose text is all template.

    Built from the document's own header text plus registry facts that do not
    change with status (status lives in the governance fields, not the text).
    """
    headers = sorted({h for c in chunks for h in c.get("page_headers", [])})
    first_line = next((l.strip() for c in chunks for l in c["content"].splitlines() if l.strip()), "")
    pages = max((c["page_end"] or 0 for c in chunks), default=0)
    first_header = headers[0] if headers else ""
    # Banner like "ARCHIVE | SUPERSEDED | GERMANY | 2019-2021": keep the pipe-separated
    # labels and drop the sentence that follows the last one.
    parts = first_line.split("|")
    banner = " | ".join([s.strip() for s in parts[:-1]] + [parts[-1].split()[0]]) if len(parts) > 1 else first_line[:80]
    # valid_to is exclusive (2022-01-01 means "through 2021").
    last_year = (doc["valid_to"] - timedelta(days=1)).year if doc["valid_to"] else doc["effective_from"].year
    text = (
        f"# {doc['title']}\n\n"
        f"Document {doc['document_id']} ({doc['document_type'].lower()}, {doc['authority'].lower().replace('_', ' ')}). "
        f"Product {doc['product']}. Jurisdiction: {', '.join(doc['countries'])}. "
        f"Period: {doc['effective_from']:%Y} to {last_year}. "
        f"{pages} pages, {'scanned and read by OCR' if extraction == 'ocr' else 'native text'}. "
        f"Page header: \"{first_header}\". Page banner: \"{banner}\"."
    )
    return {
        "chunk_id": f"{doc['document_id']}-card",
        "document_id": doc["document_id"],
        "block_type": "document_card",
        "content": text,
        "section_path": None, "table_id": None, "figure_id": None, "generated": False,
        "page_start": 1, "page_end": 1, "position": -1, "source_chunk_id": None,
        "template_share": 0.0, "boilerplate": False, "also_in": [],
    }


# -----------------------------------------------------------------------------
# h: embed, load, verify
# -----------------------------------------------------------------------------

CHUNKS_SCHEMA = [
    bigquery.SchemaField("chunk_id", "STRING", "REQUIRED", description="Stable chunk ID; the MERGE key."),
    bigquery.SchemaField("document_id", "STRING", "REQUIRED", description="Controlled document ID."),
    bigquery.SchemaField("block_type", "STRING", "REQUIRED", description="text, table, figure or document_card."),
    bigquery.SchemaField("content", "STRING", "REQUIRED", description="Chunk text shown to Gemini (generated figure text is labelled as such)."),
    bigquery.SchemaField("embedding_text", "STRING", description="Exactly what was embedded: context prefix + content."),
    bigquery.SchemaField("section_path", "STRING", description="Headings above the chunk."),
    bigquery.SchemaField("page_start", "INT64", description="First page (tables: the table block's own page). NULL for DOCX."),
    bigquery.SchemaField("page_end", "INT64"),
    bigquery.SchemaField("position", "INT64", description="Order within the document, for neighbor expansion."),
    bigquery.SchemaField("table_id", "STRING", description="e.g. 'Table 3', or the table's heading."),
    bigquery.SchemaField("figure_id", "STRING"),
    bigquery.SchemaField("qualifier", "STRING", description="Footnote that changes a table's meaning (none in this corpus)."),
    bigquery.SchemaField("generated", "BOOL", description="TRUE = model-generated text (figure description), never the only source for a number."),
    bigquery.SchemaField("extraction", "STRING", description="native or ocr."),
    bigquery.SchemaField("needs_review", "BOOL", description="TRUE = table text differs from the PDF text layer; check the original before citing."),
    bigquery.SchemaField("content_hash", "STRING"),
    bigquery.SchemaField("embed_hash", "STRING", description="Hash of embedding_text + model; unchanged = vector reused."),
    bigquery.SchemaField("boilerplate", "BOOL", description="TRUE = template text; excluded from search by default."),
    bigquery.SchemaField("template_share", "FLOAT64"),
    bigquery.SchemaField("also_in", "STRING", "REPEATED", description="Other places an identical copy appeared."),
    bigquery.SchemaField("source_chunk_id", "STRING", description="Layout Parser chunk this piece came from."),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("product", "STRING"),
    bigquery.SchemaField("countries", "STRING", "REPEATED"),
    bigquery.SchemaField("status", "STRING"),
    bigquery.SchemaField("raw_status", "STRING"),
    bigquery.SchemaField("version", "STRING"),
    bigquery.SchemaField("effective_from", "TIMESTAMP"),
    bigquery.SchemaField("valid_to", "TIMESTAMP"),
    bigquery.SchemaField("authority", "STRING"),
    bigquery.SchemaField("document_type", "STRING"),
    bigquery.SchemaField("view_url", "STRING", description="Opens the original for users with bucket read access; add #page=N for PDFs."),
    bigquery.SchemaField("source_uri", "STRING"),
    bigquery.SchemaField("embedding", "FLOAT64", "REPEATED"),
    bigquery.SchemaField("embedding_model", "STRING", description="Model@dimension that produced the vector; search compares only like with like."),
    bigquery.SchemaField("parser_version", "STRING"),
    bigquery.SchemaField("chunk_size", "INT64"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
]
COLUMNS = [f.name for f in CHUNKS_SCHEMA]


def embedding_text(p: dict) -> str:
    """Context prefix (title, version, country; never status) + the chunk text (D19)."""
    prefix = f"{p['title']} | version {p['version']} | {', '.join(p['countries'])}"
    return f"{prefix}\n\n{p['content']}"


def existing_vectors(client: bigquery.Client) -> dict:
    """embed_hash → vector for rows already in `chunks` (D22)."""
    try:
        client.get_table(table_id(BQ_CHUNKS_TABLE))
    except Exception:
        return {}
    rows = client.query(f"""
        SELECT embed_hash, ANY_VALUE(embedding) AS embedding
        FROM `{table_id(BQ_CHUNKS_TABLE)}`
        WHERE embedding_model = @model
        GROUP BY embed_hash
    """, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("model", "STRING", EMBEDDING_MODEL_TAG)])).result()
    return {r.embed_hash: list(r.embedding) for r in rows}


def other_models(client: bigquery.Client, doc_ids: list[str]) -> list[str]:
    """Embedding models used by rows this run will NOT replace (mixing check)."""
    try:
        client.get_table(table_id(BQ_CHUNKS_TABLE))
    except Exception:
        return []
    rows = client.query(f"""
        SELECT DISTINCT embedding_model FROM `{table_id(BQ_CHUNKS_TABLE)}`
        WHERE document_id NOT IN UNNEST(@docs) AND embedding_model != @model
    """, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter("docs", "STRING", doc_ids),
        bigquery.ScalarQueryParameter("model", "STRING", EMBEDDING_MODEL_TAG)])).result()
    return [r.embedding_model for r in rows]


def _embed_one(client: genai.Client, text: str, task: str) -> list[float]:
    """One embedding call with backoff on quota errors."""
    for attempt in range(6):
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL, contents=text,
                config=types.EmbedContentConfig(task_type=task, output_dimensionality=EMBEDDING_DIMENSION),
            )
            return list(response.embeddings[0].values)
        except Exception as exc:  # retry only quota / transient errors
            if attempt < 5 and any(s in str(exc) for s in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")):
                time.sleep(2 ** attempt)
                continue
            raise


def merge_into_chunks(client: bigquery.Client, rows: list[dict], doc_ids: list[str]) -> dict:
    """Staging load + MERGE; delete stale rows only for documents in this run (D23)."""
    staging = table_id(STAGING_TABLE)
    target = table_id(BQ_CHUNKS_TABLE)
    client.create_table(bigquery.Table(target, schema=CHUNKS_SCHEMA), exists_ok=True)
    client.load_table_from_json(rows, staging, job_config=bigquery.LoadJobConfig(
        schema=CHUNKS_SCHEMA, write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)).result()

    updates = ", ".join(f"{c} = S.{c}" for c in COLUMNS if c != "chunk_id")
    job = client.query(f"""
        MERGE `{target}` T
        USING `{staging}` S
        ON T.chunk_id = S.chunk_id
        WHEN MATCHED THEN UPDATE SET {updates}
        WHEN NOT MATCHED THEN INSERT ROW
        WHEN NOT MATCHED BY SOURCE AND T.document_id IN UNNEST(@docs) THEN DELETE
    """, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter("docs", "STRING", doc_ids)]))
    job.result()
    client.delete_table(staging, not_found_ok=True)
    stats = job.dml_stats
    return {"inserted": stats.inserted_row_count, "updated": stats.updated_row_count,
            "deleted": stats.deleted_row_count} if stats else {}


def verify_searchable(client: bigquery.Client, genai_client: genai.Client, doc_ids: list[str],
                      health: Health, run_start: float) -> int:
    """Probe each document through a real vector search (not just "rows written")."""
    passed = 0
    print("\n  verify-searchable probe (top 10 of all searchable chunks):")
    for doc in doc_ids:
        phrase = PROBES.get(doc, doc)
        vector = _embed_one(genai_client, phrase, "RETRIEVAL_QUERY")
        rows = list(client.query(f"""
            SELECT base.document_id, base.chunk_id, distance
            FROM VECTOR_SEARCH(
              (SELECT * FROM `{table_id(BQ_CHUNKS_TABLE)}`
               WHERE boilerplate = FALSE AND embedding_model = @model),
              'embedding',
              (SELECT @q AS embedding),
              top_k => 10, distance_type => 'COSINE')
            ORDER BY distance
        """, job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("model", "STRING", EMBEDDING_MODEL_TAG),
            bigquery.ArrayQueryParameter("q", "FLOAT64", vector)])).result())
        rank = next((i for i, r in enumerate(rows, start=1) if r.document_id == doc), None)
        ok = rank is not None
        passed += ok
        elapsed = round(time.time() - run_start, 1)
        health.record("verify_searchable", "pass" if ok else "fail", value=rank, threshold="found in top 10",
                      document_id=doc, details=f"probe: {phrase!r}; {elapsed}s since run start")
        print(f"    {'✓' if ok else '✗'} {doc:22} rank {rank if ok else '-':>2}   probe: {phrase}")
    health.record("time_to_searchable_seconds", "pass" if time.time() - run_start <= 900 else "fail",
                  value=round(time.time() - run_start, 1), threshold="<= 900 (15-min SLA)")
    return passed


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> None:
    run_start = float(os.getenv("MEDEVIDENCE_RUN_START", time.time()))
    health = Health("embed_load")
    client = bigquery.Client(project=PROJECT_ID)
    chunks, quarantine, review, extraction = load_inputs()
    docs = documents_by_id(client)

    # a. Skip quarantined files.
    chunks = [c for c in chunks if c["filename"] not in quarantine]
    health.record("quarantined_files_skipped", "warn" if quarantine else "pass", value=len(quarantine),
                  details=", ".join(sorted(quarantine)) or None)

    # b–c. Split tables out, separate figure descriptions.
    pieces, dropped_annotations = [], 0
    pages_by_file = {f: table_pages(f) for f in {c["filename"] for c in chunks}}
    for c in chunks:
        split, dropped = split_chunk(c, pages_by_file[c["filename"]])
        dropped_annotations += dropped
        for p in split:
            p.update(document_id=c["document_id"], filename=c["filename"],
                     needs_review=c["chunk_id"] in review and p["block_type"] == "table")
        pieces.extend(split)

    # d. Templates; e. exact copies within a document.
    tag_templates(pieces)
    pieces, collapsed = collapse_copies(pieces)

    # g. Document card where nothing would be searchable.
    cards = 0
    for doc_id in sorted({p["document_id"] for p in pieces}):
        own = [p for p in pieces if p["document_id"] == doc_id]
        if all(p["boilerplate"] for p in own):
            source = [c for c in chunks if c["document_id"] == doc_id]
            card = document_card(docs[doc_id], source, extraction.get(source[0]["filename"], "native"))
            card.update(filename=source[0]["filename"], needs_review=False, content_hash=_norm_hash(card["content"]))
            pieces.append(card)
            cards += 1

    # h. Governance fields, embedding text, hashes.
    now = datetime.now(timezone.utc).isoformat()
    for p in pieces:
        d = docs[p["document_id"]]
        p.update(title=d["title"], product=d["product"], countries=list(d["countries"]), status=d["status"],
                 raw_status=d["raw_status"], version=d["version"], effective_from=d["effective_from"].isoformat(),
                 valid_to=d["valid_to"].isoformat() if d["valid_to"] else None, authority=d["authority"],
                 document_type=d["document_type"], view_url=d["view_url"], source_uri=d["gcs_uri"],
                 extraction=extraction.get(p["filename"], "native"), qualifier=None,
                 embedding_model=EMBEDDING_MODEL_TAG, parser_version=PROCESSOR_VERSION,
                 chunk_size=CHUNK_SIZE, ingested_at=now)
        p["embedding_text"] = embedding_text(p)
        p["embed_hash"] = hashlib.sha256((p["embedding_text"] + EMBEDDING_MODEL_TAG).encode()).hexdigest()

    doc_ids = sorted({p["document_id"] for p in pieces})
    mixed = other_models(client, doc_ids)
    health.record("embedding_model_consistent", "fail" if mixed else "pass", value=len(mixed),
                  threshold=f"only {EMBEDDING_MODEL_TAG}", details=f"other models present: {mixed}" if mixed else None)
    if mixed:
        health.save()
        raise SystemExit(f"Stopped: rows embedded with {mixed} would be mixed with {EMBEDDING_MODEL_TAG}.")

    # Embed only what changed (D22).
    cached = existing_vectors(client)
    todo = [p for p in pieces if p["embed_hash"] not in cached]
    genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location=EMBEDDING_LOCATION)
    print(f"[embed] {len(pieces)} chunks: {len(pieces) - len(todo)} reused, {len(todo)} to embed")
    with ThreadPoolExecutor(max_workers=EMBED_WORKERS) as pool:
        vectors = list(pool.map(lambda p: _embed_one(genai_client, p["embedding_text"], "RETRIEVAL_DOCUMENT"), todo))
    for p, v in zip(todo, vectors):
        cached[p["embed_hash"]] = v
    bad_dims = 0
    for p in pieces:
        p["embedding"] = cached[p["embed_hash"]]
        bad_dims += len(p["embedding"]) != EMBEDDING_DIMENSION

    rows = [{c: p.get(c) for c in COLUMNS} for p in pieces]
    stats = merge_into_chunks(client, rows, doc_ids)
    print(f"[load]  {table_id(BQ_CHUNKS_TABLE)}: {len(rows)} rows · MERGE {stats}")

    # Health: what this stage produced.
    by_type = Counter(p["block_type"] for p in pieces)
    searchable = sum(not p["boilerplate"] for p in pieces)
    for check, value in [
        ("chunks_written", len(rows)), ("table_chunks", by_type["table"]), ("figure_chunks", by_type["figure"]),
        ("document_cards", cards), ("annotations_dropped", dropped_annotations),
        ("exact_copies_collapsed", collapsed), ("boilerplate_chunks", len(rows) - searchable),
        ("searchable_chunks", searchable), ("embeddings_new", len(todo)),
        ("embeddings_reused", len(pieces) - len(todo)),
        ("needs_review_chunks", sum(p["needs_review"] for p in pieces)),
    ]:
        health.record(check, "pass", value=value)
    health.record("embedding_dimension", "fail" if bad_dims else "pass", value=bad_dims,
                  threshold=f"all = {EMBEDDING_DIMENSION}")

    # Verify-searchable probe: the run counts as done only when search finds it.
    passed = verify_searchable(client, genai_client, doc_ids, health, run_start)
    health.save()

    print(f"\n  rows {len(rows)} · searchable {searchable} · boilerplate {len(rows) - searchable} · "
          f"tables {by_type['table']} · figures {by_type['figure']} · cards {cards} · copies collapsed {collapsed} · "
          f"needs_review {sum(p['needs_review'] for p in pieces)}")
    print(f"  verify: {passed}/{len(doc_ids)} documents found by search")
    if passed < len(doc_ids):
        raise SystemExit("Verify-searchable probe FAILED for some documents (see pipeline_health).")


if __name__ == "__main__":
    main()
