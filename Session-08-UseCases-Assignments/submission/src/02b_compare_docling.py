"""Compare Docling (open source) with Document AI Layout Parser on 3 files.

Option (b) from architecture.md §1: Layout Parser is the main parser, and a
file type moves to Docling only if Docling wins a check a demo needs.
Step 2.2 found Layout Parser rewrote "25 mg OD" as "25 mg QD" in the US
renal table, so the US label is included (decision D14).

Run with the global Python that has Docling (decision D15), not the .venv:
    source env.sh && python3 src/02b_compare_docling.py

Docling settings (decision D16): OCR off, because these files have a text
layer and Docling then reads that text directly; table structure on.
Layout Parser results come from output/chunks_cs512.json (Step 2.2), so this
script makes no Document AI calls and costs nothing.

Writes output/docling/<file>.md (Docling's output, for reading) and
output/docling_comparison.json, and prints a side-by-side table.
"""

from __future__ import annotations

import json
import re
import time

from config import CORPUS_DIR, OUTPUT_DIR


FILES = {
    "DE_AX17_Current_Label_v4.2.pdf": "DE-AX17-LBL-042",
    "US_AX17_Prescribing_Information_v5.0.pdf": "US-AX17-PI-050",
    "SB_AX17_2026_09_Safety_Bulletin.docx": "SB-AX17-2026-09",
}

# Rows exactly as printed in the source (read from the PDF text layer in
# Step 1, and from the DOCX table cells). A row passes only if every cell
# matches word for word.
EXPECTED_ROWS = {
    "DE-AX17-LBL-042": [
        ["Renal category", "eGFR", "Starting dose", "Maximum", "Monitoring"],
        ["Normal", ">=90", "50 mg OD", "100 mg/day", "Routine"],
        ["Mild", "60-89", "50 mg OD", "100 mg/day", "Routine"],
        ["Moderate", "30-59", "25 mg OD", "50 mg/day", "Recheck 2-4 weeks"],
        ["Severe", "15-29", "Specialist review", "25 mg/day", "Enhanced"],
    ],
    "US-AX17-PI-050": [
        ["Population", "US recommendation"],
        ["Moderate renal impairment", "25 mg OD; reassess"],
        ["Severe", "Specialist assessment"],
        ["Dialysis", "Insufficient evidence"],
    ],
    "SB-AX17-2026-09": [
        ["Signal", "Threshold", "Action", "Authority"],
        ["ALT/AST", ">3x ULN", "Medical review", "Bulletin"],
        ["Bilirubin", ">2x ULN", "Urgent review", "Bulletin"],
        ["Mild isolated change", "Below trigger", "Repeat test", "Protocol"],
    ],
}

# Bulletin header fields that must survive (demo 3 cites them).
BULLETIN_FIELDS = ["APPROVED - HIGH AUTHORITY", "07-Oct-2026 10:00 CET", "Germany, Singapore, UAE",
                   "repeat testing between Day 14 and Day 21"]


def _table_rows(markdown: str) -> list[list[str]]:
    """All Markdown table rows as lists of trimmed cells (separator rows skipped)."""
    rows = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [re.sub(r"\s+", " ", c).strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def _row_check(markdown: str, expected: list[list[str]]) -> dict:
    """Which expected rows appear word for word."""
    parsed = _table_rows(markdown)
    found = [row for row in expected if row in parsed]
    return {"rows_exact": f"{len(found)}/{len(expected)}",
            "missing": [" | ".join(r) for r in expected if r not in parsed]}


def _headings(markdown: str) -> dict:
    """Heading count by level, from Markdown '#' lines."""
    levels: dict = {}
    for line in markdown.splitlines():
        m = re.match(r"^(#{1,6})\s+\S", line)
        if m:
            levels[len(m.group(1))] = levels.get(len(m.group(1)), 0) + 1
    return {f"h{k}": v for k, v in sorted(levels.items())}


def run_docling(path) -> tuple[str, dict]:
    """Convert one file with Docling; return Markdown and structural facts."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})

    start = time.perf_counter()
    doc = converter.convert(str(path)).document
    seconds = round(time.perf_counter() - start, 1)

    tables = []
    for t in doc.tables:
        page = t.prov[0].page_no if getattr(t, "prov", None) else None
        tables.append({"page": page, "caption": t.caption_text(doc) or None})
    pictures = [{"page": p.prov[0].page_no if getattr(p, "prov", None) else None,
                 "caption": p.caption_text(doc) or None} for p in doc.pictures]
    return doc.export_to_markdown(), {"seconds": seconds, "tables": tables, "pictures": pictures}


def layout_parser_text(document_id: str) -> tuple[str, dict]:
    """Layout Parser's output for the same file, from Step 2.2's chunks."""
    rows = [r for r in json.loads((OUTPUT_DIR / "chunks_cs512.json").read_text(encoding="utf-8"))
            if r["document_id"] == document_id]
    text = "\n\n".join(r["content"] for r in rows)
    tables = [{"page": r["page_start"]} for r in rows if "table" in r["block_kinds"]]
    pictures = [{"page": r["page_start"]} for r in rows if "image" in r["block_kinds"]]
    return text, {"seconds": "~60–80 (cloud, online)", "tables": tables, "pictures": pictures}


def compare(document_id: str, text: str, facts: dict) -> dict:
    """The checklist for one parser on one file."""
    result = {
        **_row_check(text, EXPECTED_ROWS[document_id]),
        "headings": _headings(text),
        "tables_found": len(facts["tables"]),
        "table_pages": sorted({t["page"] for t in facts["tables"] if t.get("page")}),
        "figures_found": len(facts["pictures"]),
        "seconds": facts["seconds"],
    }
    if document_id == "US-AX17-PI-050":
        result["verbatim_25mg_OD"] = "25 mg OD" in text and "25 mg QD" not in text
    if document_id == "SB-AX17-2026-09":
        result["header_fields"] = f"{sum(f in text for f in BULLETIN_FIELDS)}/{len(BULLETIN_FIELDS)}"
    return result


def main() -> None:
    out_dir = OUTPUT_DIR / "docling"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}

    for filename, document_id in FILES.items():
        print(f"[docling] {filename} ...", flush=True)
        md, facts = run_docling(CORPUS_DIR / filename)
        (out_dir / f"{filename.rsplit('.', 1)[0]}.md").write_text(md, encoding="utf-8")
        lp_text, lp_facts = layout_parser_text(document_id)
        report[document_id] = {"layout_parser": compare(document_id, lp_text, lp_facts),
                               "docling": compare(document_id, md, facts)}

    print("\nSide by side (✅ = passes)\n")
    for document_id, both in report.items():
        print(f"  {document_id}")
        keys = [k for k in both["docling"] if k != "missing"]
        for key in keys:
            lp, dl = both["layout_parser"].get(key), both["docling"].get(key)
            print(f"    {key:18} Layout Parser: {str(lp):34} Docling: {dl}")
        for parser in ("layout_parser", "docling"):
            if both[parser]["missing"]:
                print(f"    {parser} missing rows: {both[parser]['missing']}")
        print()

    (OUTPUT_DIR / "docling_comparison.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote output/docling_comparison.json and output/docling/*.md")


if __name__ == "__main__":
    main()
