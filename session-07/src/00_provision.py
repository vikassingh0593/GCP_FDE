"""Provision the small set of resources required by Project 1.

This script is intentionally conservative:
- It creates only lab-scoped resources.
- It does not grant broad IAM roles.
- Existing resources are reused when possible.
"""

from __future__ import annotations

from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud import bigquery, documentai, storage

from config import (
    BIGQUERY_LOCATION,
    BQ_DATASET,
    DOCUMENT_AI_LOCATION,
    GCS_BUCKET,
    PROCESSOR_ID_FILE,
    PROCESSOR_NAME,
    PROJECT_ID,
    SOURCE_PDF,
)


def ensure_bucket() -> None:
    """Create the source-document bucket if it does not already exist."""
    client = storage.Client(project=PROJECT_ID)
    try:
        bucket = client.get_bucket(GCS_BUCKET)
        print(f"[reuse] gs://{bucket.name}")
    except NotFound:
        bucket = client.bucket(GCS_BUCKET)
        bucket.location = "US"
        client.create_bucket(bucket)
        print(f"[create] gs://{bucket.name}")

    blob = bucket.blob(SOURCE_PDF.name)
    blob.upload_from_filename(SOURCE_PDF)
    print(f"[upload] gs://{GCS_BUCKET}/{SOURCE_PDF.name}")


def ensure_bigquery_dataset() -> None:
    """Create the BigQuery dataset used for chunk storage and retrieval."""
    client = bigquery.Client(project=PROJECT_ID)
    dataset_id = f"{PROJECT_ID}.{BQ_DATASET}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = BIGQUERY_LOCATION
    try:
        client.create_dataset(dataset)
        print(f"[create] BigQuery dataset {dataset_id}")
    except AlreadyExists:
        print(f"[reuse] BigQuery dataset {dataset_id}")


def ensure_layout_processor() -> None:
    """Create a Document AI Layout Parser processor and persist its ID."""
    PROCESSOR_ID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PROCESSOR_ID_FILE.exists():
        print(f"[reuse] processor id {PROCESSOR_ID_FILE.read_text().strip()}")
        return

    client = documentai.DocumentProcessorServiceClient(
        client_options={
            "api_endpoint": f"{DOCUMENT_AI_LOCATION}-documentai.googleapis.com"
        }
    )
    parent = client.common_location_path(PROJECT_ID, DOCUMENT_AI_LOCATION)

    processor = documentai.Processor(
        display_name=PROCESSOR_NAME,
        type_="LAYOUT_PARSER_PROCESSOR",
    )
    created = client.create_processor(parent=parent, processor=processor)
    processor_id = created.name.rsplit("/", 1)[-1]
    PROCESSOR_ID_FILE.write_text(processor_id, encoding="utf-8")
    print(f"[create] Document AI processor {processor_id}")


def main() -> None:
    """Provision all lab resources."""
    ensure_bucket()
    ensure_bigquery_dataset()
    ensure_layout_processor()


if __name__ == "__main__":
    main()
