#!/usr/bin/env bash
# Retail Order Exception Control Tower: one-time local setup.
# Run from retail-control-tower/:   bash setup.sh
#
# What it does: checks Python, creates .venv, installs requirements, makes sure
# lab.env exists, and checks gcloud login and project. It creates NO cloud
# resources: the bucket, dataset and tables come from scripts/load_data.
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================================"
echo " Retail Order Exception Control Tower: setup"
echo "============================================================"

# ---------- 1. Python 3.10+ (ADK needs it) ----------
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "Python 3.10+ needed, found $(python3 --version)"; exit 1; }

# ---------- 2. Virtual environment + packages ----------
if [ ! -d .venv ]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
# Exact tested versions when the lock file exists; the ranges in requirements.txt otherwise.
if [ -f requirements.lock ]; then python -m pip install -r requirements.lock; else python -m pip install -r requirements.txt; fi

# ---------- 3. lab.env ----------
if [ ! -f lab.env ]; then
  cp lab.env.example lab.env
  echo
  echo "Created lab.env from lab.env.example."
  echo "Review it (at least IDENTITY_SALT), then run setup.sh again."
  exit 0
fi
# shellcheck disable=SC1091
source lab.env
mkdir -p "${OUTPUT_DIR:-output}"

# ---------- 4. gcloud login and project ----------
command -v gcloud >/dev/null || { echo "gcloud CLI not found"; exit 1; }

ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"
[ -n "$ACCOUNT" ] || { echo "Not logged in. Run: gcloud auth login"; exit 1; }

gcloud auth application-default print-access-token >/dev/null 2>&1 || {
  echo "No application-default credentials. Run:"
  echo "  gcloud auth application-default login"
  echo "  gcloud auth application-default set-quota-project $GOOGLE_CLOUD_PROJECT"
  exit 1
}

CURRENT_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [ "$CURRENT_PROJECT" != "$GOOGLE_CLOUD_PROJECT" ]; then
  echo "gcloud project is '$CURRENT_PROJECT', lab.env says '$GOOGLE_CLOUD_PROJECT'. Run:"
  echo "  gcloud config set project $GOOGLE_CLOUD_PROJECT"
  exit 1
fi

# ---------- 5. Google Cloud APIs (read-only check; enabling them is your call) ----------
# If gcloud itself can't list services (e.g. its login needs re-authentication), say so instead of
# reporting every API as missing. The scripts use application-default credentials, not this login.
MISSING=""
if ENABLED="$(gcloud services list --enabled --format='value(config.name)' 2>/dev/null)"; then
  for api in bigquery.googleapis.com storage.googleapis.com documentai.googleapis.com \
             aiplatform.googleapis.com discoveryengine.googleapis.com; do
    echo "$ENABLED" | grep -qx "$api" || MISSING="$MISSING $api"
  done
else
  echo "NOTE: could not list enabled APIs (gcloud login may need: gcloud auth login). Skipping that check."
fi
if [ -n "$MISSING" ]; then
  echo "WARNING: these APIs are not enabled in $GOOGLE_CLOUD_PROJECT:$MISSING"
  echo "  Enable them:  gcloud services enable$MISSING"
fi

# ---------- 6. Offline tests ----------
if ls tests/test_*.py >/dev/null 2>&1; then
  python -m pytest -q tests
fi

cat <<EOF

SETUP COMPLETE
  account: $ACCOUNT
  project: $GOOGLE_CLOUD_PROJECT
  dataset: $BQ_DATASET   bucket: gs://$GCS_BUCKET

Every new shell:
  source .venv/bin/activate && source lab.env

Run order (see README.md):
  python data/generate_data.py && python -m scripts.load_data   # before each test or demo session
  python -m scripts.ingest_docs                                 # once, and when documents change
  python -m fulfilment_specialist.server                        # terminal 1
  python -m web.server                                          # terminal 2 -> http://127.0.0.1:8080
EOF
