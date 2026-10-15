"""Provision the Google Cloud resources MedEvidence needs.

Creates, or reuses when they already exist:
- Cloud Storage bucket, with the allowlisted corpus files uploaded under raw/
- BigQuery dataset for the chunks, documents and adverse_events tables
- Document AI Layout Parser processor, with its ID saved to .state/

Safe to re-run: every step checks before it creates or uploads anything.
Pattern from session-07/src/00_provision.py, with two changes:
- a file is uploaded only if it is new or its content changed (MD5 check);
- an existing processor is found by name, so a lost .state file never
  creates a duplicate.
"""

from __future__ import annotations

import base64
import hashlib

from google.api_core.exceptions import NotFound
from google.cloud import bigquery, documentai, storage

from config import (
    BIGQUERY_LOCATION,
    BQ_DATASET,
    CORPUS_DIR,
    DEMO_OUTPUTS_DIR,
    DOCUMENT_AI_LOCATION,
    GCS_BUCKET,
    GCS_RAW_PREFIX,
    OUTPUT_DIR,
    PROCESSOR_ID_FILE,
    PROCESSOR_NAME,
    PROJECT_ID,
    SOURCE_FILES,
    STATE_DIR,
)


def _local_md5(path) -> str:
    """Return a file's MD5 in the base64 form Cloud Storage reports."""
    digest = hashlib.md5(path.read_bytes()).digest()
    return base64.b64encode(digest).decode("ascii")


def ensure_bucket() -> None:
    """Create the bucket if needed and upload the allowlisted corpus files.

    Cloud Storage is the source Document AI reads from. Only files in
    SOURCE_FILES are uploaded, so the answer key never leaves the laptop.
    """
    client = storage.Client(project=PROJECT_ID)
    try:
        bucket = client.get_bucket(GCS_BUCKET)
        print(f"[reuse]  gs://{bucket.name}")
    except NotFound:
        bucket = client.bucket(GCS_BUCKET)
        # One permission model for the whole bucket, managed with IAM only.
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True
        # "US" multi-region, the same as the BigQuery dataset.
        client.create_bucket(bucket, location="US")
        print(f"[create] gs://{bucket.name}")

    for filename in SOURCE_FILES:
        local_path = CORPUS_DIR / filename
        blob = bucket.blob(f"{GCS_RAW_PREFIX}/{filename}")

        # Upload only when the file is missing or its content changed.
        # Re-runs stay fast, and an edited file is never silently kept stale.
        if blob.exists():
            blob.reload()
            if blob.md5_hash == _local_md5(local_path):
                print(f"[same]   {filename}")
                continue

        blob.upload_from_filename(local_path)
        print(f"[upload] gs://{GCS_BUCKET}/{GCS_RAW_PREFIX}/{filename}")


def ensure_bigquery_dataset() -> None:
    """Create the dataset that will hold the chunks, documents and AE tables.

    Tables are created later by the loading scripts. This step only creates
    the container and fixes its location.
    """
    client = bigquery.Client(project=PROJECT_ID)
    dataset_id = f"{PROJECT_ID}.{BQ_DATASET}"

    # Look first, create only on NotFound (same rule as the bucket).
    # Session-07 caught AlreadyExists, but BigQuery raises the broader
    # Conflict (409), so its second run crashed instead of reusing.
    try:
        client.get_dataset(dataset_id)
        print(f"[reuse]  BigQuery dataset {dataset_id}")
    except NotFound:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = BIGQUERY_LOCATION
        dataset.description = "MedEvidence (Session 8, Challenge 01) - vks"
        client.create_dataset(dataset)
        print(f"[create] BigQuery dataset {dataset_id}")


def ensure_layout_processor() -> None:
    """Create a Document AI Layout Parser processor and save its ID.

    The ID goes to .state/ so later scripts can call the processor without
    looking it up again.
    """
    PROCESSOR_ID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PROCESSOR_ID_FILE.exists():
        print(f"[reuse]  processor id {PROCESSOR_ID_FILE.read_text().strip()}")
        return

    # Document AI is regional, so the client must call the regional endpoint.
    client = documentai.DocumentProcessorServiceClient(
        client_options={
            "api_endpoint": f"{DOCUMENT_AI_LOCATION}-documentai.googleapis.com"
        }
    )
    parent = client.common_location_path(PROJECT_ID, DOCUMENT_AI_LOCATION)

    # If the .state file was lost, find the processor by name instead of
    # creating a second one.
    for existing in client.list_processors(parent=parent):
        if existing.display_name == PROCESSOR_NAME:
            processor_id = existing.name.rsplit("/", 1)[-1]
            PROCESSOR_ID_FILE.write_text(processor_id, encoding="utf-8")
            print(f"[found]  Document AI processor {processor_id}")
            return

    processor = documentai.Processor(
        display_name=PROCESSOR_NAME,
        type_="LAYOUT_PARSER_PROCESSOR",
    )
    created = client.create_processor(parent=parent, processor=processor)
    processor_id = created.name.rsplit("/", 1)[-1]
    PROCESSOR_ID_FILE.write_text(processor_id, encoding="utf-8")
    print(f"[create] Document AI processor {processor_id}")


def main() -> None:
    """Provision every resource, then the local working folders."""
    for folder in (OUTPUT_DIR, STATE_DIR, DEMO_OUTPUTS_DIR):
        folder.mkdir(parents=True, exist_ok=True)

    ensure_bucket()
    ensure_bigquery_dataset()
    ensure_layout_processor()


if __name__ == "__main__":
    main()
