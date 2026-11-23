#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lab.env"
gcloud config set project "$PROJECT_ID"
gcloud auth application-default login
echo "Active project:"
gcloud config get-value project
