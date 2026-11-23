"""Read-only preflight: is everything in place for a demo or an eval run?

Run from retail-control-tower/, before the demo:

    python -m scripts.check_gcp

Checks, without creating or changing anything:
  1. Application Default Credentials work for the project in lab.env.
  2. The dataset and every table exist, with rows (operational tables, register, doc_chunks).
  3. The data is fresh enough for the demo (newest inventory snapshot vs the max age).
  4. The bucket holds the registered PDFs.
  5. The Document AI processor ID is saved (ingest_docs has run).
  6. Gemini and the embedding model answer one tiny request.
  7. The Fulfilment Specialist's Agent Card is reachable.

Exit code 0 = ready; 1 = something to fix (each line says what to run).
"""

from __future__ import annotations

import sys

from common import config
from common.utils import log

problems: list[str] = []


def check(label: str, ok: bool, fix: str = "") -> None:
    log("ok" if ok else "FAIL", label)
    if not ok:
        problems.append(f"{label}: {fix}" if fix else label)


def main() -> None:
    print(f"project {config.PROJECT_ID} | dataset {config.BQ_DATASET} | bucket gs://{config.GCS_BUCKET}\n")
    try:
        import google.auth
        _, project = google.auth.default()
        check("application default credentials", True)
    except Exception as exc:  # noqa: BLE001
        check("application default credentials", False, f"gcloud auth application-default login ({exc})")
        sys.exit("\nNOT READY:\n  - " + "\n  - ".join(problems))

    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery, storage

    bq = bigquery.Client(project=config.PROJECT_ID, location=config.BIGQUERY_LOCATION)
    tables = list(config.OPERATIONAL_TABLES.values()) + [config.BQ_DOCUMENT_REGISTER_TABLE, config.BQ_DOC_CHUNKS_TABLE]
    for table in tables:
        try:
            rows = bq.get_table(config.table_id(table)).num_rows
            fix = "python -m scripts.ingest_docs" if table == config.BQ_DOC_CHUNKS_TABLE else \
                "python data/generate_data.py && python -m scripts.load_data"
            check(f"table {table}: {rows} rows", rows > 0, fix)
        except NotFound:
            check(f"table {table}", False, "missing; run scripts.load_data (or scripts.ingest_docs for doc_chunks)")

    try:
        age = list(bq.query(f"SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(snapshot_at), MINUTE) AS age "
                            f"FROM `{config.table_id(config.OPERATIONAL_TABLES['inventory'])}`").result())[0].age
        check(f"newest inventory snapshot {age} min old (max {config.INVENTORY_MAX_AGE_MINUTES})",
              age is not None and age <= config.INVENTORY_MAX_AGE_MINUTES - 30,
              "data is about to go stale: python data/generate_data.py && python -m scripts.load_data")
    except NotFound:
        pass

    try:
        blobs = [b.name for b in storage.Client(project=config.PROJECT_ID).list_blobs(
            config.GCS_BUCKET, prefix=f"{config.GCS_DOCS_PREFIX}/") if b.name.endswith(".pdf")]
        check(f"bucket holds {len(blobs)} PDFs", len(blobs) > 0, "python -m scripts.load_data")
    except NotFound:
        check("bucket", False, "python -m scripts.load_data")

    check("Document AI processor ID saved", config.DOCUMENT_AI_PROCESSOR_ID_FILE.exists(), "python -m scripts.ingest_docs")

    from google import genai
    from google.genai import types
    # Keep each client in a variable: google-genai closes a Client that is garbage-collected
    # mid-call ("the client has been closed").
    try:
        model_client = genai.Client(vertexai=True, project=config.PROJECT_ID, location=config.VERTEX_LOCATION)
        model_client.models.generate_content(
            model=config.ORCHESTRATOR_MODEL, contents="Reply with OK.",
            config=types.GenerateContentConfig(max_output_tokens=5))
        check(f"model {config.ORCHESTRATOR_MODEL}", True)
    except Exception as exc:  # noqa: BLE001
        check(f"model {config.ORCHESTRATOR_MODEL}", False, f"not available ({str(exc)[:120]}); set ORCHESTRATOR_MODEL")
    try:
        embed_client = genai.Client(vertexai=True, project=config.PROJECT_ID, location=config.EMBEDDING_LOCATION)
        embed_client.models.embed_content(
            model=config.EMBEDDING_MODEL, contents="ok",
            config=types.EmbedContentConfig(output_dimensionality=config.EMBEDDING_DIMENSION))
        check(f"embedding model {config.EMBEDDING_MODEL}@{config.EMBEDDING_DIMENSION}", True)
    except Exception as exc:  # noqa: BLE001
        check(f"embedding model {config.EMBEDDING_MODEL}", False, str(exc)[:120])

    import httpx
    try:
        ok = httpx.get(config.FULFILMENT_AGENT_CARD_URL, timeout=3).status_code == 200
    except httpx.HTTPError:
        ok = False
    check(f"Fulfilment Specialist card {config.FULFILMENT_AGENT_CARD_URL}", ok, "python -m fulfilment_specialist.server")

    if problems:
        sys.exit("\nNOT READY:\n  - " + "\n  - ".join(problems))
    print("\nREADY.")


if __name__ == "__main__":
    main()
