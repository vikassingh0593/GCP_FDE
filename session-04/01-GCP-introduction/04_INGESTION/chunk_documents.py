from pathlib import Path
import json, re

SRC = Path("../02_DATA/documents")
OUT = Path("generated_chunks.jsonl")

def parse_frontmatter(text):
    meta = {}
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        for line in fm.strip().splitlines():
            if ":" in line:
                k,v=line.split(":",1)
                meta[k.strip()] = v.strip().strip('"')
        return meta, body.strip()
    return meta, text

def section_chunks(body):
    # Preserve heading + all paragraphs belonging to that heading.
    current_heading = "Document"
    buf = []
    for line in body.splitlines():
        if line.startswith("## "):
            if buf:
                yield current_heading, "\n".join(buf).strip()
            current_heading = line[3:].strip()
            buf = []
        elif line.startswith("# "):
            continue
        else:
            buf.append(line)
    if buf:
        yield current_heading, "\n".join(buf).strip()

rows=[]
for path in sorted(SRC.glob("*.md")):
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    seq=0
    for section, content in section_chunks(body):
        content=content.strip()
        if not content:
            continue
        seq += 1
        rows.append({
            "chunk_id": f"{meta.get('source_id', path.stem)}-C{seq:03d}",
            "source_id": meta.get("source_id", path.stem),
            "title": meta.get("title", path.stem),
            "status": meta.get("status", "UNKNOWN"),
            "version": meta.get("version", "UNKNOWN"),
            "section": section,
            "content": content,
            "source_uri": f"gs://vikas-rag-v1/raw/documents/{path.name}"
        })

with OUT.open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print(f"Wrote {len(rows)} chunks to {OUT}")
for r in rows:
    print(r["chunk_id"], "|", r["status"], "|", r["section"])
