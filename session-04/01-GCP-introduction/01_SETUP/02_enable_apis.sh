#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lab.env"
gcloud services enable   bigquery.googleapis.com   storage.googleapis.com   aiplatform.googleapis.com   discoveryengine.googleapis.com
echo "Required APIs requested/enabled."
