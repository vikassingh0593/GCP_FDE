#!/usr/bin/env python3
"""Render the runbooks and postmortems as PDFs, plus the document register.

In an enterprise, runbooks and postmortems arrive as PDFs from a document
system, and their metadata (ID, version, status, dates, owner) lives in that
system's register, not inside the file. This tool produces exactly that:

    data/docs_source/**/*.md          authoring source (edit these; never uploaded)
        │  python data/build_docs.py
        ▼
    data/docs/runbooks/*.pdf          what load_data uploads and Document AI parses
    data/docs/postmortems/*.pdf
    data/docs/document_register.csv   one row per document: the metadata source of truth
    data/schemas/document_register.json

Every PDF has a real text layer except PM-2025-052, which is rendered as an
image-only scan: Document AI must run OCR to read it. The script checks both
facts with pypdf before finishing.

Output is deterministic (fixed PDF dates and IDs), so an unchanged document
keeps the same MD5 and load_data doesn't re-upload it. Run it only when a
source document changes; the daily routine is generate_data + load_data.
"""

from __future__ import annotations

import csv
import html
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pypdf import PdfReader
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

rl_config.invariant = 1                      # same input -> byte-identical PDF

DATA_DIR = Path(__file__).resolve().parent
SOURCE_DIR = DATA_DIR / "docs_source"
DOCS_DIR = DATA_DIR / "docs"
REGISTER_FILE = DOCS_DIR / "document_register.csv"
REGISTER_SCHEMA_FILE = DATA_DIR / "schemas" / "document_register.json"

SCANNED_DOCS = {"PM-2025-052"}               # rendered as image-only: needs OCR

# (column, BigQuery type, mode, description)
REGISTER_SCHEMA = [
    ("doc_id", "STRING", "REQUIRED", "Document ID, e.g. RB-CAR-003"),
    ("version", "STRING", "REQUIRED", "Document version; postmortems are version 1"),
    ("status", "STRING", "REQUIRED", "current | superseded. Only current documents are evidence"),
    ("doc_type", "STRING", "REQUIRED", "runbook | postmortem"),
    ("title", "STRING", "REQUIRED", "Document title"),
    ("file_path", "STRING", "REQUIRED", "Path under data/docs/ and under the bucket's docs prefix"),
    ("media", "STRING", "REQUIRED", "pdf_text (has a text layer) | pdf_scan (image only, needs OCR)"),
    ("exception_type", "STRING", "NULLABLE", "inventory_shortage, allocation, carrier_delay, payment_hold, "
                                             "warehouse_disruption or recent_change"),
    ("owner", "STRING", "NULLABLE", "Owning team (runbooks)"),
    ("effective_date", "DATE", "NULLABLE", "Runbooks: when this version took effect"),
    ("supersedes", "STRING", "NULLABLE", "Runbooks: the version this one replaced"),
    ("superseded_by", "STRING", "NULLABLE", "Runbooks: the version that replaced this one"),
    ("superseded_date", "DATE", "NULLABLE", "Runbooks: when this version stopped being current"),
    ("incident_date", "DATE", "NULLABLE", "Postmortems: date of the incident"),
    ("warehouse_id", "STRING", "NULLABLE", "Warehouse the document is about, if one"),
    ("carrier", "STRING", "NULLABLE", "Carrier the document is about, if one"),
    ("region", "STRING", "NULLABLE", "Region (postmortems)"),
    ("root_cause_category", "STRING", "NULLABLE", "Postmortems: root-cause category"),
    ("severity", "STRING", "NULLABLE", "Postmortems: SEV level"),
    ("duration_hours", "INTEGER", "NULLABLE", "Postmortems: incident duration"),
]

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


# -----------------------------------------------------------------------------
# Read the markdown sources
# -----------------------------------------------------------------------------

def read_source(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(text)
    if not match:
        raise SystemExit(f"{path}: no front matter")
    meta = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        meta[key.strip()] = "" if value.lower() == "none" else value
    return meta, text[match.end():]


def register_row(meta: dict, file_path: str) -> dict:
    is_runbook = meta["doc_type"] == "runbook"
    row = {c[0]: "" for c in REGISTER_SCHEMA}
    row.update({k: v for k, v in meta.items() if k in row})
    row["version"] = meta.get("version") or "1"
    row["status"] = meta.get("status") or "current"
    row["file_path"] = file_path
    row["media"] = "pdf_scan" if meta["doc_id"] in SCANNED_DOCS else "pdf_text"
    if not is_runbook:
        row["effective_date"] = ""
    return row


# -----------------------------------------------------------------------------
# Markdown body -> simple blocks (headings, paragraphs, numbered and bulleted lists)
# -----------------------------------------------------------------------------

def blocks(body: str) -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    items: list[tuple[str, str, int]] = []          # (kind, text, indent)

    def flush():
        if items:
            out.append(("list", list(items)))
            items.clear()

    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        if line.startswith("# "):
            flush(); out.append(("h1", line[2:].strip()))
        elif line.startswith("## "):
            flush(); out.append(("h2", line[3:].strip()))
        elif re.match(r"^\s*\d+\.\s", line):
            indent = len(line) - len(line.lstrip())
            items.append(("num", re.sub(r"^\s*\d+\.\s", "", line), indent))
        elif re.match(r"^\s*-\s", line):
            indent = len(line) - len(line.lstrip())
            items.append(("bullet", re.sub(r"^\s*-\s", "", line), indent))
        elif items:                                   # continuation of a list item
            kind, text, indent = items[-1]
            items[-1] = (kind, f"{text} {line.strip()}", indent)
        else:
            flush(); out.append(("p", line.strip()))
    flush()
    return out


def inline(text: str) -> str:
    """Escape, then **bold** and `code`, for reportlab's mini-markup."""
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', text)


def plain(text: str) -> str:
    return re.sub(r"[*`]", "", text)


# -----------------------------------------------------------------------------
# Text PDF (has a text layer)
# -----------------------------------------------------------------------------

STYLES = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=STYLES["Heading1"], fontSize=17, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=STYLES["Heading2"], fontSize=13, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("Body", parent=STYLES["BodyText"], fontSize=10, leading=13.5)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=8.5, leading=11)


def control_table(row: dict) -> Table:
    """The document-control box a document system prints on page 1."""
    if row["doc_type"] == "runbook":
        pairs = [("Document ID", row["doc_id"]), ("Version", row["version"]), ("Status", row["status"].upper()),
                 ("Effective date", row["effective_date"]), ("Owner", row["owner"]),
                 ("Superseded by", row["superseded_by"] or "-")]
    else:
        pairs = [("Document ID", row["doc_id"]), ("Incident date", row["incident_date"]),
                 ("Severity", row["severity"]), ("Region", row["region"]),
                 ("Warehouse", row["warehouse_id"] or "-"), ("Carrier", row["carrier"] or "-")]
    data = [[Paragraph(f"<b>{k}</b>", SMALL), Paragraph(html.escape(v or "-"), SMALL)] for k, v in pairs]
    table = Table([data[i] + data[i + 1] for i in range(0, len(data), 2)], colWidths=[28 * mm, 52 * mm] * 2)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                               ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                               ("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def list_paragraphs(items: list[tuple[str, str, int]]) -> list[Paragraph]:
    """Each item is its own paragraph with a literal "1." or bullet, so step numbers stay in the text
    layer (chunking splits long sections at step starts) and nested bullets keep their indent."""
    out, number = [], 0
    for kind, text, indent in items:
        level = 1 if indent == 0 else 2
        if kind == "num":
            number += 1
            prefix = f"{number}."
        else:
            prefix = "•"
        style = ParagraphStyle(f"li{level}", parent=BODY, leftIndent=8 * mm * level, firstLineIndent=-5 * mm,
                               spaceAfter=2)
        out.append(Paragraph(f"{prefix}&nbsp;&nbsp;{inline(text)}", style))
    return out


def render_text_pdf(row: dict, body: str, out: Path) -> None:
    story = [control_table(row), Spacer(1, 6 * mm)]
    for kind, content in blocks(body):
        if kind == "h1":
            story.append(Paragraph(inline(content), H1))
        elif kind == "h2":
            story.append(Paragraph(inline(content), H2))
        elif kind == "p":
            story.append(Paragraph(inline(content), BODY))
        else:
            story.extend(list_paragraphs(content))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(18 * mm, 10 * mm, f"Internal - {row['doc_id']} v{row['version']} - {row['title']}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title=row["title"], author=row.get("owner") or "Operations", subject=row["doc_id"])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


# -----------------------------------------------------------------------------
# Scanned PDF (image only: no text layer, needs OCR)
# -----------------------------------------------------------------------------

def _font(size: int, bold: bool = False):
    try:
        return ImageFont.load_default(size=size)       # Pillow >= 10.1: scalable, same on every OS
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render_scanned_pdf(row: dict, body: str, out: Path) -> None:
    """Draw the document onto page images (150 dpi, slight skew and speckle), saved as an image-only PDF."""
    dpi, width, height, margin = 150, 1240, 1754, 110
    rng = random.Random(row["doc_id"])                  # deterministic "scan noise"
    fonts = {"h1": _font(34), "h2": _font(26), "p": _font(21), "small": _font(19)}
    lines: list[tuple[str, str]] = [
        ("small", f"Document ID: {row['doc_id']}    Incident date: {row['incident_date']}    "
                  f"Severity: {row['severity']}    Region: {row['region']}"),
        ("small", f"Warehouse: {row['warehouse_id'] or '-'}    Carrier: {row['carrier'] or '-'}"),
        ("gap", ""),
    ]
    for kind, content in blocks(body):
        if kind in ("h1", "h2", "p"):
            lines.append((kind, plain(content)))
        else:
            for n, (item_kind, text, _indent) in enumerate(content, start=1):
                lines.append(("p", f"{n}. {plain(text)}" if item_kind == "num" else f"- {plain(text)}"))
        lines.append(("gap", ""))

    pages, page, draw, y = [], None, None, 0

    def new_page():
        nonlocal page, draw, y
        page = Image.new("L", (width, height), 250)
        draw = ImageDraw.Draw(page)
        y = margin
        pages.append(page)

    new_page()
    for kind, text in lines:
        if kind == "gap":
            y += 14
            continue
        font = fonts[kind]
        for wrapped in _wrap(draw, text, font, width - 2 * margin):
            line_height = int(font.size * 1.45) if hasattr(font, "size") else 24
            if y + line_height > height - margin:
                new_page()
            draw.text((margin, y), wrapped, fill=25, font=font)
            y += line_height
        if kind in ("h1", "h2"):
            y += 6

    finished = []
    for img in pages:
        for _ in range(900):                                # toner speckle
            img.putpixel((rng.randrange(width), rng.randrange(height)), rng.randrange(120, 200))
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        img = img.rotate(rng.uniform(-0.8, 0.8), resample=Image.BICUBIC, fillcolor=250)
        finished.append(img.convert("RGB"))
    out.parent.mkdir(parents=True, exist_ok=True)
    fixed = time.gmtime(datetime(2025, 10, 10, tzinfo=timezone.utc).timestamp())  # same input -> same bytes
    finished[0].save(out, "PDF", resolution=dpi, save_all=True, append_images=finished[1:],
                     title=row["title"], creationDate=fixed, modDate=fixed)


# -----------------------------------------------------------------------------

def check_pdf(row: dict, path: Path, body: str) -> list[str]:
    text = "".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if row["media"] == "pdf_scan":
        return [] if not text.strip() else [f"{row['doc_id']}: scanned PDF has a text layer"]
    problems = []
    if row["doc_id"] not in text:
        problems.append(f"{row['doc_id']}: document ID not found in the text layer")
    for kind, heading in blocks(body):
        if kind == "h2" and plain(heading).split()[0] not in text:
            problems.append(f"{row['doc_id']}: heading '{heading}' not found in the text layer")
    return problems


def main() -> None:
    sources = sorted(SOURCE_DIR.rglob("*.md"))
    if not sources:
        raise SystemExit(f"no sources under {SOURCE_DIR}")
    rows, problems = [], []
    for src in sources:
        meta, body = read_source(src)
        relative = src.relative_to(SOURCE_DIR).with_suffix(".pdf").as_posix()
        row = register_row(meta, relative)
        out = DOCS_DIR / relative
        (render_scanned_pdf if row["media"] == "pdf_scan" else render_text_pdf)(row, body, out)
        problems += check_pdf(row, out, body)
        rows.append(row)
        print(f"  {row['media']:<9} {relative}")

    keys = [(r["doc_id"], r["version"]) for r in rows]
    if len(keys) != len(set(keys)):
        problems.append("duplicate (doc_id, version) in the register")
    for row in rows:
        if row["superseded_by"] and row["status"] != "superseded":
            problems.append(f"{row['doc_id']} v{row['version']}: has superseded_by but status {row['status']}")

    columns = [c[0] for c in REGISTER_SCHEMA]
    with REGISTER_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["doc_type"], r["doc_id"], r["version"])))
    REGISTER_SCHEMA_FILE.write_text(json.dumps(
        [{"name": n, "type": t, "mode": m, "description": d} for n, t, m, d in REGISTER_SCHEMA], indent=2) + "\n",
        encoding="utf-8")

    stale = sorted(p.relative_to(DOCS_DIR).as_posix() for p in DOCS_DIR.rglob("*.pdf")
                   if p.relative_to(DOCS_DIR).as_posix() not in {r["file_path"] for r in rows})
    for path in stale:
        (DOCS_DIR / path).unlink()
        print(f"  removed   {path} (no longer has a source)")

    if problems:
        sys.exit("BUILD FAILED:\n  - " + "\n  - ".join(problems))
    print(f"\n{len(rows)} PDFs ({sum(r['media'] == 'pdf_scan' for r in rows)} scanned) "
          f"-> {DOCS_DIR.relative_to(DATA_DIR.parent)}/, register -> {REGISTER_FILE.relative_to(DATA_DIR.parent)}")


if __name__ == "__main__":
    main()
