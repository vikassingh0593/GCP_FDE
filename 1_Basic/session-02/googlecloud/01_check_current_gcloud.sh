#!/usr/bin/env bash
set -u
echo "======================================================================"
echo " CURRENT GOOGLE CLOUD STATE — READ ONLY"
echo "======================================================================"
if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud NOT installed. Install: https://cloud.google.com/sdk/docs/install"; exit 1
fi
echo; echo "[gcloud version]"; gcloud --version | head -n 1
echo; echo "[active configuration]"
gcloud config configurations list --filter="is_active:true" --format="table(name,is_active)"
echo; echo "[configuration properties]"; gcloud config list
echo; echo "[configured project]"; gcloud config get-value project 2>/dev/null
echo; echo "[CLI accounts]"; gcloud auth list --format="table(account,status)"
echo; echo "[relevant environment]"
echo "GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT:-<not set>}"
echo "GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION:-<not set>}"
echo "GOOGLE_CLOUD_QUOTA_PROJECT=${GOOGLE_CLOUD_QUOTA_PROJECT:-<not set>}"
echo "GOOGLE_GENAI_USE_VERTEXAI=${GOOGLE_GENAI_USE_VERTEXAI:-<not set>}"
echo "CLOUDSDK_ACTIVE_CONFIG_NAME=${CLOUDSDK_ACTIVE_CONFIG_NAME:-<not set>}"
echo; echo "[ADC]"
if gcloud auth application-default print-access-token >/dev/null 2>&1; then echo "ADC: AVAILABLE"; else echo "ADC: NOT AVAILABLE"; fi
echo; echo "[projects visible to current identity]"
gcloud projects list --limit=30 --format="table(projectId,name)" || true
echo; echo "Nothing was changed by this script."
