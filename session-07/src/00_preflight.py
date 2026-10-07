"""Fail early when the most common cloud configuration problems are present."""

from __future__ import annotations

import google.auth
from google.cloud import bigquery, storage

from config import GCS_BUCKET, PROCESSOR_ID_FILE, PROJECT_ID


def main() -> None:
    """Validate credentials and lab resources before expensive API calls."""
    credentials, detected_project = google.auth.default(
        quota_project_id=PROJECT_ID
    )
    print(f"ADC project hint : {detected_project}")
    print(f"Configured project: {PROJECT_ID}")
    print(f"Credentials type : {type(credentials).__name__}")

    storage.Client(project=PROJECT_ID).get_bucket(GCS_BUCKET)
    bigquery.Client(project=PROJECT_ID).query("SELECT 1").result()

    if not PROCESSOR_ID_FILE.exists():
        raise RuntimeError("Document AI processor ID file is missing.")

    print("Preflight: PASS")


if __name__ == "__main__":
    main()
