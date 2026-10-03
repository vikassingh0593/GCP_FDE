#!/usr/bin/env bash
set -euo pipefail
source "../01_SETUP/lab.env"
gcloud storage cp ../02_DATA/documents/*.md "gs://$BUCKET/raw/documents/"
gcloud storage ls "gs://$BUCKET/raw/documents/"
