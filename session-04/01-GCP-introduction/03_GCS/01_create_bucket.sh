#!/usr/bin/env bash
set -euo pipefail
source "../01_SETUP/lab.env"

if gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  echo "Bucket gs://$BUCKET already exists and is accessible."
else
  gcloud storage buckets create "gs://$BUCKET"     --project="$PROJECT_ID"     --location="$LOCATION"     --default-storage-class=STANDARD     --uniform-bucket-level-access
fi

gcloud storage buckets describe "gs://$BUCKET"   --format="yaml(name,location,storageClass,iamConfiguration.uniformBucketLevelAccess)"
