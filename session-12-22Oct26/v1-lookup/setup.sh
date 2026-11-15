#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

cat <<'EOF'

Setup complete.

First time:
  cp env.sh.example env.sh
  # Set GOOGLE_CLOUD_PROJECT to the exact project ID.
  source env.sh

Authentication:
  gcloud auth login
  gcloud auth application-default login
  gcloud config set project "$GOOGLE_CLOUD_PROJECT"
  gcloud auth application-default set-quota-project "$GOOGLE_CLOUD_PROJECT"

Run:
  python src/00_preflight.py
  python src/01_context_and_anatomy.py
  python src/02_enterprise_runner.py
  python src/03_harness_torture_test.py

EOF
