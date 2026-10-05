#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# H2 Compact Setup
#
# Purpose:
#   1. Enable required Google Cloud APIs
#   2. Create the Cloud Storage bucket if it does not exist
#   3. Create the BigQuery dataset if it does not exist
#   4. Install required Python packages
#
# Safe to run multiple times.
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load lab configuration.
source "${SCRIPT_DIR}/lab.env"


# -----------------------------------------------------------------------------
# Step 1 — Enable Google Cloud APIs
# -----------------------------------------------------------------------------

printf '\n[1/4] Enabling required Google Cloud APIs...\n'

gcloud services enable \
  aiplatform.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  --project="${GOOGLE_CLOUD_PROJECT}"


# -----------------------------------------------------------------------------
# Step 2 — Create Cloud Storage bucket
# -----------------------------------------------------------------------------

printf '\n[2/4] Creating Cloud Storage bucket if needed...\n'

BUCKET_URI="gs://${H2_COMPACT_BUCKET}"

if gcloud storage buckets describe "${BUCKET_URI}" >/dev/null 2>&1; then

  echo "Bucket already exists: ${BUCKET_URI}"

else

  echo "Creating bucket: ${BUCKET_URI}"

  gcloud storage buckets create "${BUCKET_URI}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --location="${GOOGLE_CLOUD_LOCATION}"

fi


# -----------------------------------------------------------------------------
# Step 3 — Create BigQuery dataset
# -----------------------------------------------------------------------------

printf '\n[3/4] Creating BigQuery dataset if needed...\n'

DATASET_REF="${GOOGLE_CLOUD_PROJECT}:${H2_COMPACT_DATASET}"

if bq show "${DATASET_REF}" >/dev/null 2>&1; then

  echo "Dataset already exists: ${DATASET_REF}"

else

  echo "Creating dataset: ${DATASET_REF}"

  bq --location="${GOOGLE_CLOUD_LOCATION}" mk \
    --dataset \
    "${DATASET_REF}"

fi


# -----------------------------------------------------------------------------
# Step 4 — Install Python dependencies
# -----------------------------------------------------------------------------

printf '\n[4/4] Installing Python packages...\n'

python -m pip install \
  -r "${SCRIPT_DIR}/requirements.txt"


# -----------------------------------------------------------------------------
# Complete
# -----------------------------------------------------------------------------

printf '\n------------------------------------------------------------\n'
printf 'H2 Compact setup complete.\n'
printf '------------------------------------------------------------\n'

printf '\nProject : %s\n' "${GOOGLE_CLOUD_PROJECT}"
printf 'Bucket  : gs://%s\n' "${H2_COMPACT_BUCKET}"
printf 'Dataset : %s.%s\n' \
  "${GOOGLE_CLOUD_PROJECT}" \
  "${H2_COMPACT_DATASET}"

printf '\nNext step:\n'
printf 'python 02_BOOTSTRAP/bootstrap.py\n\n'