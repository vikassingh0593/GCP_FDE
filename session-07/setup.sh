#!/usr/bin/env bash
set -euo pipefail

[[ -f env.sh ]] || { echo "ERROR: cp env.sh.example env.sh and edit it first."; exit 1; }
source env.sh

if [[ "${GOOGLE_CLOUD_PROJECT}" == "YOUR_PROJECT_ID" ]]; then
  echo "ERROR: Set GOOGLE_CLOUD_PROJECT in env.sh."
  exit 1
fi

echo "============================================================"
echo "TREDENCE FDE — PROJECT 1 SETUP"
echo "============================================================"
echo "Configured project : ${GOOGLE_CLOUD_PROJECT}"
echo "Active gcloud      : $(gcloud config get-value project 2>/dev/null)"
echo "Active account     : $(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -1)"

gcloud config set project "${GOOGLE_CLOUD_PROJECT}"
gcloud config set billing/quota_project "${GOOGLE_CLOUD_PROJECT}" || true

echo
echo "[1/5] Enabling APIs..."
gcloud services enable   aiplatform.googleapis.com   bigquery.googleapis.com   documentai.googleapis.com   discoveryengine.googleapis.com   storage.googleapis.com   serviceusage.googleapis.com

echo
echo "[2/5] Checking ADC..."
gcloud auth application-default print-access-token >/dev/null || {
  echo "ADC missing. Run: gcloud auth application-default login"
  exit 1
}

echo
echo "[3/5] Creating Python environment..."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "[4/5] Provisioning resources..."
mkdir -p .state output
python src/00_provision.py

echo
echo "[5/5] Preflight..."
python src/00_preflight.py

echo
echo "READY."
echo "Next: source .venv/bin/activate && python src/01_parse_document.py"
