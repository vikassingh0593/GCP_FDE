#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/training.env"
echo "========== TREDENCE FDE STATUS =========="
echo "Expected config : $TREDENCE_GCLOUD_CONFIG"
echo "Expected project: $GOOGLE_CLOUD_PROJECT"
echo "Location        : $GOOGLE_CLOUD_LOCATION"
echo "Model           : $MODEL_ID"
echo
echo "Active config   : $(gcloud config configurations list --filter='is_active:true' --format='value(name)')"
echo "gcloud project  : $(gcloud config get-value project 2>/dev/null)"
echo "CLI account     : $(gcloud auth list --filter=status:ACTIVE --format='value(account)')"
if gcloud auth application-default print-access-token >/dev/null 2>&1; then echo "ADC             : OK"; else echo "ADC             : FAILED"; fi
echo "Quota project   : $GOOGLE_CLOUD_QUOTA_PROJECT"
echo "Vertex API      : $(gcloud services list --enabled --project="$GOOGLE_CLOUD_PROJECT" --filter='name:aiplatform.googleapis.com' --format='value(name)')"
echo "Vertex mode     : $GOOGLE_GENAI_USE_VERTEXAI"
