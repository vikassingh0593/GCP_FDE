"""Quality gate for the parsed chunks (Step 2.2), run before anything is embedded.

Reads output/chunks_cs<size>.json (from 02_parse.py) and checks every file:
 1. pages in (pypdf) = pages out (chunk page spans); no empty pages
 2. OCR pages: pages with no text layer (pypdf finds < 50 characters)
 3. junk-character ratio
 4. known phrases that must survive parsing
 5. table intact: each known table in ONE chunk with its title, header and rows
 6. boundary: no chunk ends mid-sentence (headings, captions, table rows are fine)
 7. injection scan: instruction-like text quarantines the file
 8. generated text: how many chunks carry image annotations (moved out of the text)
 9. template paragraphs and exact duplicates (input for Step 2.4 dedup)
10. faithfulness: words in the parser's output that are not in the PDF's own
    text layer (Layout Parser can normalize text, e.g. "OD" → "QD")

Writes output/parse_report.json and output/quarantine.json (files Step 2.4
must skip), and compares chunk sizes for the §2 experiment log. No API calls,
so it can be re-run any time without cost.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict

from pypdf import PdfReader

from config import CORPUS_DIR, OUTPUT_DIR
from health import Health


# Phrases that must be found in a document's chunks (case-insensitive).
KNOWN_PHRASES = {
    "DE-AX17-LBL-042": ["Table 3. Renal dose modification", "Supersedes: DE-AX17-LBL-038"],
    "DE-AX17-LBL-038": ["Historical renal dosing", "SUPERSEDED"],
    "US-AX17-PI-050": ["Not authoritative for German regulatory guidance"],
    "HN-204": ["Table 14. Treatment-emergent adverse events", "Table 18. Renal subgroup summary"],
    "HN-311": ["Table 14. Treatment-emergent adverse events", "Table 18. Renal subgroup summary"],
    "HN-402": ["Table 14. Treatment-emergent adverse events", "Table 18. Renal subgroup summary"],
    "SB-AX17-2026-09": ["SB-AX17-2026-09", "repeat testing between Day 14 and Day 21"],
    "DE-AX17-HSL-2019-2021": ["ARCHIVE"],
}

# Must appear on EVERY page of the scanned letters (proves OCR read each page).
SCAN_ID = "DE-AX17-HSL-2019-2021"
SCAN_PAGE_PHRASE = "SCANNED HISTORICAL AX-17 SAFETY LETTER"

# Known tables: every term must be inside one single chunk.
TABLE_3 = ["Renal category", "eGFR", "Starting dose", "Maximum", "Monitoring", "Moderate", "Severe", "25 mg OD"]
TABLE_14 = ["Table 14", "Adverse event", "AX-17 %", "Control %", "Serious", "Nausea", "Rash", "Transaminase"]
TABLE_18 = ["Table 18", "Renal stratum", "Exposure ratio", "Interpretation", "Normal", "Severe"]
KNOWN_TABLES = {
    ("DE-AX17-LBL-042", "Table 3"): TABLE_3,
    ("DE-AX17-LBL-038", "Historical renal dosing"): ["Historical renal dosing", "Renal category", "Historical starting dose", "Moderate", "50 mg OD", "SUPERSEDED"],
    ("US-AX17-PI-050", "US renal recommendations"): ["US renal recommendations", "Population", "US recommendation", "Moderate renal impairment", "Dialysis"],
    ("HN-204", "Table 14"): TABLE_14, ("HN-311", "Table 14"): TABLE_14, ("HN-402", "Table 14"): TABLE_14,
    ("HN-204", "Table 18"): TABLE_18, ("HN-311", "Table 18"): TABLE_18, ("HN-402", "Table 18"): TABLE_18,
    ("SB-AX17-2026-09", "Signal table"): ["Signal", "Threshold", "Action", "Authority", "ALT/AST", "Bilirubin", "Mild isolated change"],
}

# Text a controlled document should never contain (§8, layer 3).
INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)|^\s*system\s*(note)?\s*:|"
    r"you are now|disregard (all|the|previous)|new instructions",
    re.I | re.M,
)

# The template paragraph (section A): same wording, different numbers.
TEMPLATE = re.compile(r"evidence package for [A-Za-z |]+ included \d+ evaluable participants", re.I)

# Characters we expect in clinical text; anything else counts as junk.
NORMAL_CHARS = re.compile(r"[A-Za-z0-9\s.,;:%()/\-|+<>=≥≤'\"_&#*\[\]!?–—·•°×µ]")

# Standard footer printed on every page of the corpus; not part of a sentence.
FOOTER = "Synthetic training corpus - not for clinical use"

# Word pattern for the faithfulness comparison.
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-/%]*[A-Za-z0-9%]|[A-Za-z0-9]")

OCR_TEXT_LAYER_MIN = 50   # characters on a page below which the page needed OCR
MAX_JUNK_RATIO = 0.15
TEMPLATE_ONLY_SHARE = 0.9


def _pdf_text_layer(path) -> list[str]:
    """Each page's text layer (empty for scanned pages)."""
    return [(page.extract_text() or "").strip() for page in PdfReader(path).pages]


def _template_share(content: str) -> float:
    """Share of the chunk's text (headings excluded) made of template paragraphs."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip() and not p.lstrip().startswith("#")]
    total = sum(len(p) for p in paras) or 1
    return sum(len(p) for p in paras if TEMPLATE.search(p)) / total


def _ends_mid_sentence(content: str) -> bool:
    """True if the last line looks like a sentence cut off before its end."""
    text = content.replace(FOOTER, "").rstrip()
    last = text.splitlines()[-1].strip() if text.strip() else ""
    if not last or last.startswith(("#", "|")) or len(last) < 100:
        return False  # heading, table row, caption or short label
    return last[-1] not in ".!?:;)\"'"


def check_file(filename: str, rows: list[dict]) -> dict:
    """All checks for one file at one chunk size."""
    doc_id = rows[0]["document_id"]
    text = "\n".join(r["content"] for r in rows)
    lower = text.lower()
    result = {"document_id": doc_id, "filename": filename, "chunks": len(rows), "problems": [], "notes": []}

    # 1–2. Pages and OCR (PDF only; a DOCX has no fixed pages).
    if filename.lower().endswith(".pdf"):
        pages_text = _pdf_text_layer(CORPUS_DIR / filename)
        layer = [len(t) for t in pages_text]
        covered = {p for r in rows if r["page_start"] for p in range(r["page_start"], (r["page_end"] or r["page_start"]) + 1)}
        missing = sorted(set(range(1, len(layer) + 1)) - covered)
        result.update(pages_in=len(layer), pages_out=max(covered, default=0),
                      ocr_pages=sum(1 for n in layer if n < OCR_TEXT_LAYER_MIN))
        if missing:
            result["problems"].append(f"pages with no chunk: {missing}")
    else:
        result.update(pages_in=None, pages_out=None, ocr_pages=0)
        result["notes"].append("DOCX: no fixed pages, cite by section")

    # 3. Junk characters.
    junk = sum(1 for ch in text if not NORMAL_CHARS.match(ch))
    result["junk_ratio"] = round(junk / max(len(text), 1), 4)
    if result["junk_ratio"] > MAX_JUNK_RATIO:
        result["problems"].append(f"junk ratio {result['junk_ratio']}")

    # 4. Known phrases.
    result["phrases_missing"] = [p for p in KNOWN_PHRASES.get(doc_id, []) if p.lower() not in lower]
    if result["phrases_missing"]:
        result["problems"].append(f"known phrases missing: {result['phrases_missing']}")
    if doc_id == SCAN_ID:
        pages_with = {
            r["page_start"] for r in rows
            if SCAN_PAGE_PHRASE.lower() in (r["content"] + " " + " ".join(r.get("page_headers", []))).lower()
        }
        result["scan_pages_with_phrase"] = f"{len(pages_with)}/{result['pages_in']}"
        if len(pages_with) < (result["pages_in"] or 0):
            result["problems"].append(f"scan phrase found on only {len(pages_with)} of {result['pages_in']} pages")

    # 5. Tables intact.
    tables = {}
    for (table_doc, table_name), terms in KNOWN_TABLES.items():
        if table_doc != doc_id:
            continue
        whole = [r["chunk_id"] for r in rows if all(t.lower() in r["content"].lower() for t in terms)]
        partial = [r["chunk_id"] for r in rows if any(t.lower() in r["content"].lower() for t in terms[1:3])]
        tables[table_name] = {"intact": bool(whole), "chunk": whole[0] if whole else None,
                              "pieces": [] if whole else partial}
    result["tables"] = tables

    # 6. Boundaries.
    cut = [r["chunk_id"] for r in rows if _ends_mid_sentence(r["content"])]
    result["mid_sentence_endings"] = cut

    # 7. Injection.
    hits = [r["chunk_id"] for r in rows if INJECTION.search(r["content"])]
    result["injection_hits"] = hits
    if hits:
        result["problems"].append(f"instruction-like text in {hits}")

    # 8. Generated annotations (already moved out of `content` by 02_parse.py).
    result["chunks_with_annotations"] = sum(1 for r in rows if r.get("annotations"))

    # 10. Faithfulness (native PDFs only; scanned pages have no text layer to compare).
    if filename.lower().endswith(".pdf") and result["ocr_pages"] == 0:
        layer_words = {w.lower() for w in WORD.findall(" ".join(pages_text))}
        novel = Counter(w.lower() for r in rows for w in WORD.findall(r["content"]) if w.lower() not in layer_words)
        # A changed word inside a table row is the dangerous case (e.g. a dose string).
        review = [r["chunk_id"] for r in rows if "|" in r["content"]
                  and any(w.lower() not in layer_words for line in r["content"].splitlines() if line.startswith("|")
                          for w in WORD.findall(line))]
        result["faithfulness"] = {"words_not_in_source": dict(novel.most_common(10)), "table_chunks_to_review": review}
        if review:
            result["notes"].append(f"table text differs from the PDF in {review}: review before citing")

    # 9. Templates and exact duplicates.
    shares = [_template_share(r["content"]) for r in rows]
    result["template_only_chunks"] = sum(1 for s in shares if s >= TEMPLATE_ONLY_SHARE)
    hashes = Counter(hashlib.sha256(re.sub(r"\s+", " ", r["content"].lower()).encode()).hexdigest() for r in rows)
    result["exact_duplicate_chunks"] = sum(n - 1 for n in hashes.values() if n > 1)

    result["quarantine"] = bool(result["problems"])
    return result


def run(size: int) -> list[dict]:
    """Check every file at one chunk size."""
    path = OUTPUT_DIR / f"chunks_cs{size}.json"
    by_file = defaultdict(list)
    for r in json.loads(path.read_text(encoding="utf-8")):
        by_file[r["filename"]].append(r)
    return [check_file(f, rows) for f, rows in by_file.items()]


def record_health(results: list[dict], size: int) -> None:
    """Store each file's gate results in BigQuery `pipeline_health`."""
    health = Health("parse_gate")
    for r in results:
        doc = r["document_id"]
        health.record("parse_gate", "fail" if r["quarantine"] else "pass", value=len(r["problems"]),
                      threshold="0 problems", document_id=doc, details="; ".join(r["problems"]) or None)
        health.record("chunks", "pass", value=r["chunks"], document_id=doc, details=f"chunk size {size}")
        if r["pages_in"]:
            health.record("pages_in_equals_out", "pass" if r["pages_out"] == r["pages_in"] else "fail",
                          value=r["pages_out"], threshold=f"= {r['pages_in']}", document_id=doc)
            health.record("ocr_pages", "pass", value=r["ocr_pages"], document_id=doc)
        health.record("junk_ratio", "pass" if r["junk_ratio"] <= MAX_JUNK_RATIO else "fail",
                      value=r["junk_ratio"], threshold=f"<= {MAX_JUNK_RATIO}", document_id=doc)
        if r["tables"]:
            intact = sum(t["intact"] for t in r["tables"].values())
            health.record("tables_intact", "pass" if intact == len(r["tables"]) else "fail", value=intact,
                          threshold=f"= {len(r['tables'])}", document_id=doc)
        health.record("injection_hits", "fail" if r["injection_hits"] else "pass",
                      value=len(r["injection_hits"]), threshold="= 0", document_id=doc)
        health.record("mid_sentence_endings", "warn" if r["mid_sentence_endings"] else "pass",
                      value=len(r["mid_sentence_endings"]), threshold="= 0", document_id=doc,
                      details="covered at answer time by neighbor expansion" if r["mid_sentence_endings"] else None)
        faith = r.get("faithfulness")
        if faith is not None:
            diffs = faith["table_chunks_to_review"]
            health.record("faithfulness_table_diffs", "warn" if diffs else "pass", value=len(diffs),
                          threshold="= 0 (vs PDF text layer)", document_id=doc,
                          details=f"review {diffs}; words not in source: {faith['words_not_in_source']}" if diffs else None)
    health.save()


def main() -> None:
    sizes = sorted(int(p.stem.split("cs")[1]) for p in OUTPUT_DIR.glob("chunks_cs*.json"))
    report = {size: run(size) for size in sizes}

    main_size = 512 if 512 in report else sizes[0]
    print(f"Quality gate at chunk size {main_size}\n")
    print(f"  {'document':22} {'chunks':>6} {'pages':>7} {'OCR':>4} {'junk':>6} {'tables intact':>14} {'cut':>4} {'tmpl':>5} {'dup':>4}  result")
    for r in report[main_size]:
        pages = f"{r['pages_out']}/{r['pages_in']}" if r["pages_in"] else "docx"
        intact = f"{sum(t['intact'] for t in r['tables'].values())}/{len(r['tables'])}" if r["tables"] else "-"
        verdict = "QUARANTINE: " + "; ".join(r["problems"]) if r["quarantine"] else "pass"
        print(f"  {r['document_id']:22} {r['chunks']:6} {pages:>7} {r['ocr_pages']:4} {r['junk_ratio']:6} "
              f"{intact:>14} {len(r['mid_sentence_endings']):4} {r['template_only_chunks']:5} {r['exact_duplicate_chunks']:4}  {verdict}")
        if r.get("scan_pages_with_phrase"):
            print(f"  {'':22} scan phrase on {r['scan_pages_with_phrase']} pages")
        for name, t in r["tables"].items():
            if not t["intact"]:
                print(f"  {'':22} table '{name}' SPLIT; chunks with header terms: {t['pieces'][:4]}")
        faith = r.get("faithfulness", {})
        if faith.get("words_not_in_source"):
            print(f"  {'':22} words not in the PDF text layer: {faith['words_not_in_source']}")
        for note in r["notes"]:
            if "differs" in note:
                print(f"  {'':22} REVIEW: {note}")

    print("\nChunk-size experiment (§2 log)")
    print(f"  {'size':>5} {'chunks':>7} {'template-only':>14} {'exact dups':>11} {'tables intact':>14} {'mid-sentence':>13} {'with annotations':>17}")
    for size in sizes:
        rs = report[size]
        tables = [t for r in rs for t in r["tables"].values()]
        print(f"  {size:5} {sum(r['chunks'] for r in rs):7} {sum(r['template_only_chunks'] for r in rs):14} "
              f"{sum(r['exact_duplicate_chunks'] for r in rs):11} {sum(t['intact'] for t in tables):>8}/{len(tables):<5} "
              f"{sum(len(r['mid_sentence_endings']) for r in rs):13} {sum(r['chunks_with_annotations'] for r in rs):17}")

    record_health(report[main_size], main_size)

    quarantine = [r["filename"] for r in report[main_size] if r["quarantine"]]
    (OUTPUT_DIR / "parse_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUTPUT_DIR / "quarantine.json").write_text(json.dumps(quarantine, indent=2), encoding="utf-8")
    print(f"\nQuarantined files: {quarantine or 'none'}")
    print("Wrote output/parse_report.json and output/quarantine.json")


if __name__ == "__main__":
    main()
