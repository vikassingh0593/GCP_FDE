"""Check that everything MedEvidence needs is reachable before real work starts.

Run it any time, especially in a new terminal or after a login expires:
    python src/00_preflight.py

Every check runs, even after a failure, and the script prints one PASS/FAIL
line per check, so you see every problem at once. It exits with code 1 if
anything failed.

Pattern from session-07/src/00_preflight.py. That version checked that the
resources exist; this one also makes one tiny real call to each AI service
(embedding, Gemini, Ranking API). That proves the API is enabled and your
account may use it, before Step 2 spends minutes parsing documents.
"""

from __future__ import annotations

import sys

import google.auth
from google import genai
from google.cloud import bigquery, documentai, storage
from google.cloud import discoveryengine_v1 as discoveryengine
from google.genai import types

from config import (
    AE_REGISTRY_CSV,
    BIGQUERY_LOCATION,
    BQ_DATASET,
    CORPUS_DIR,
    DOCUMENT_AI_LOCATION,
    DOCUMENT_REGISTRY_CSV,
    EMBEDDING_DIMENSION,
    EMBEDDING_LOCATION,
    EMBEDDING_MODEL,
    GCS_BUCKET,
    GCS_RAW_PREFIX,
    GENERATION_MODEL,
    PROCESSOR_ID_FILE,
    PROJECT_ID,
    RANKING_MODEL,
    SOURCE_FILES,
    VERTEX_LOCATION,
)


# -----------------------------------------------------------------------------
# Checks: each returns a short detail string on success, or raises on failure
# -----------------------------------------------------------------------------

def check_login() -> str:
    """Application Default Credentials: the login every Python client uses."""
    credentials, _ = google.auth.default(quota_project_id=PROJECT_ID)
    return f"{type(credentials).__name__}, quota project {PROJECT_ID}"


def check_local_corpus() -> str:
    """The allowlisted files and both CSVs exist where config.py expects them."""
    missing = [f for f in SOURCE_FILES if not (CORPUS_DIR / f).exists()]
    missing += [p.name for p in (DOCUMENT_REGISTRY_CSV, AE_REGISTRY_CSV) if not p.exists()]
    if missing:
        raise FileNotFoundError(f"missing in {CORPUS_DIR}: {missing}")
    return f"{len(SOURCE_FILES)} source files + 2 CSVs"


def check_bucket() -> str:
    """Cloud Storage holds exactly the allowlisted files under raw/."""
    bucket = storage.Client(project=PROJECT_ID).get_bucket(GCS_BUCKET)
    prefix = f"{GCS_RAW_PREFIX}/"
    uploaded = {b.name.removeprefix(prefix) for b in bucket.list_blobs(prefix=prefix)}

    missing = set(SOURCE_FILES) - uploaded
    extra = uploaded - set(SOURCE_FILES)  # e.g. the answer key, which must never be there
    if missing or extra:
        raise RuntimeError(f"missing={sorted(missing)} unexpected={sorted(extra)}")
    return f"{len(uploaded)}/{len(SOURCE_FILES)} files in gs://{GCS_BUCKET}/{prefix}"


def check_bigquery() -> str:
    """The dataset exists in the right location and we may run query jobs."""
    client = bigquery.Client(project=PROJECT_ID)
    dataset = client.get_dataset(f"{PROJECT_ID}.{BQ_DATASET}")
    if dataset.location != BIGQUERY_LOCATION:
        raise RuntimeError(f"dataset is in {dataset.location}, expected {BIGQUERY_LOCATION}")

    # A trivial query proves we hold the "create query job" permission.
    client.query("SELECT 1").result()
    return f"{BQ_DATASET} in {dataset.location}, query jobs OK"


def check_processor() -> str:
    """The Layout Parser processor exists and is enabled."""
    if not PROCESSOR_ID_FILE.exists():
        raise RuntimeError("no processor ID in .state/. Run src/00_provision.py first")

    client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{DOCUMENT_AI_LOCATION}-documentai.googleapis.com"}
    )
    name = client.processor_path(
        PROJECT_ID, DOCUMENT_AI_LOCATION, PROCESSOR_ID_FILE.read_text().strip()
    )
    processor = client.get_processor(name=name)
    if processor.state.name != "ENABLED":
        raise RuntimeError(f"processor state is {processor.state.name}")
    return f"{processor.display_name} ({processor.type_}) ENABLED"


def check_embedding() -> str:
    """One tiny embedding call: model reachable and the vector size is right."""
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=EMBEDDING_LOCATION)
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents="moderate renal impairment",
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=EMBEDDING_DIMENSION,
            ),
        )
    finally:
        client.close()

    size = len(response.embeddings[0].values)
    if size != EMBEDDING_DIMENSION:
        raise RuntimeError(f"got {size} numbers, expected {EMBEDDING_DIMENSION}")
    return f"{EMBEDDING_MODEL} returned {size} numbers"


def check_gemini() -> str:
    """One tiny Gemini call: the model that writes answers and runs the agent."""
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)
    try:
        response = client.models.generate_content(
            model=GENERATION_MODEL,
            contents="Reply with exactly the word OK.",
            config=types.GenerateContentConfig(temperature=0),
        )
    finally:
        client.close()
    return f"{GENERATION_MODEL} replied {response.text.strip()!r}"


def check_ranking() -> str:
    """One tiny Ranking API call that should put the relevant passage first."""
    client = discoveryengine.RankServiceClient()
    request = discoveryengine.RankRequest(
        ranking_config=client.ranking_config_path(
            project=PROJECT_ID,
            location="global",
            ranking_config="default_ranking_config",
        ),
        model=RANKING_MODEL,
        top_n=2,
        query="starting dose for moderate renal impairment",
        records=[
            discoveryengine.RankingRecord(id="storage", content="Store below 25 °C in the original package."),
            discoveryengine.RankingRecord(id="renal", content="Moderate renal impairment: start at 25 mg once daily."),
        ],
    )
    records = client.rank(request=request).records
    if records[0].id != "renal":
        raise RuntimeError(f"ranked {records[0].id!r} first, expected 'renal'")
    return f"renal passage ranked first (score {records[0].score:.2f})"


CHECKS = [
    ("Login (ADC)", check_login),
    ("Local corpus", check_local_corpus),
    ("Cloud Storage", check_bucket),
    ("BigQuery", check_bigquery),
    ("Document AI", check_processor),
    ("Embeddings", check_embedding),
    ("Gemini", check_gemini),
    ("Ranking API", check_ranking),
]


def main() -> None:
    """Run every check, print a PASS/FAIL line for each, exit 1 on any failure."""
    failures = 0
    for label, check in CHECKS:
        try:
            print(f"[PASS] {label:14} {check()}")
        except Exception as exc:  # report every problem, then keep going
            failures += 1
            first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
            print(f"[FAIL] {label:14} {type(exc).__name__}: {first_line[:160]}")

    passed = len(CHECKS) - failures
    print(f"\nPreflight: {'PASS' if not failures else 'FAIL'} ({passed}/{len(CHECKS)})")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
