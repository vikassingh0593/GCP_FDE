# MedEvidence Large Synthetic Corpus

Synthetic training corpus for the Tredence FDE MedEvidence assignment. It intentionally mixes native PDFs, an image-only scanned PDF, DOCX, CSV, tables, charts, QR and Code128 barcode content.

Key engineering purpose:
- compare native layout parsing with OCR-required scanned content;
- preserve table headers, captions, headings and page context;
- test current vs superseded evidence;
- test Germany vs US jurisdiction;
- test exact identifiers such as DE-AX17-LBL-042 and SB-AX17-2026-09;
- decide whether CSV registries belong in vector ingestion or structured lookup;
- exercise overlap, parent-child/neighbor expansion and duplicate retrieval;
- provide enough volume for realistic Top-K/reranking/index experiments.

All medical content is fictional and must not be used clinically.
