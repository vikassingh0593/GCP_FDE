#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lab.env"
printf '\n[1/4] Enabling APIs...\n'
gcloud services enable aiplatform.googleapis.com bigquery.googleapis.com storage.googleapis.com --project="${GOOGLE_CLOUD_PROJECT}"
printf '\n[2/4] Creating bucket if needed...\n'
if ! gcloud storage buckets describe "gs://${TEXT2SQL_BUCKET}" >/dev/null 2>&1; then gcloud storage buckets create "gs://${TEXT2SQL_BUCKET}" --project="${GOOGLE_CLOUD_PROJECT}" --location="${GOOGLE_CLOUD_LOCATION}"; else echo "Bucket exists."; fi
printf '\n[3/4] Creating dataset if needed...\n'
if ! bq show "${GOOGLE_CLOUD_PROJECT}:${TEXT2SQL_DATASET}" >/dev/null 2>&1; then bq --location="${GOOGLE_CLOUD_LOCATION}" mk --dataset "${GOOGLE_CLOUD_PROJECT}:${TEXT2SQL_DATASET}"; else echo "Dataset exists."; fi
printf '\n[4/4] Installing Python packages...\n'
python -m pip install -r "${SCRIPT_DIR}/requirements.txt"
printf '\nSetup complete. Next: python 02_BOOTSTRAP/bootstrap.py\n'
