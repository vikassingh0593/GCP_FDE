# Structure-aware chunking

This lab uses **section-aware chunks**, not arbitrary fixed 500-token windows.

Why? The evidence unit in a policy is normally a complete clause/section. We want `7.4.2 Offline Store Exception` to survive intact, together with source/version/status provenance.

Run:

```bash
cd 04_INGESTION
python3 chunk_documents.py
head -3 generated_chunks.jsonl
```

Expected: roughly 10–12 chunks, including separate chunks for V3 freshness, V3 clause 7.4.2, legacy freshness and replenishment rules.

Then upload:

```bash
source ../01_SETUP/lab.env
gcloud storage cp generated_chunks.jsonl "gs://$BUCKET/derived/chunks/"
```
