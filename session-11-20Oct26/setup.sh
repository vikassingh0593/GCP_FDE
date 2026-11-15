#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# 0.1 — Local Python environment setup
# ---------------------------------------------------------------------------
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

cat <<'EOF'

Setup complete.

First-time configuration:
  cp env.sh.example env.sh
  # Verify GOOGLE_CLOUD_PROJECT is the exact project ID.

For every new terminal:
  source .venv/bin/activate
  source env.sh

Google Cloud authentication:
  gcloud auth login
  gcloud auth application-default login

Useful project checks:
  gcloud projects list
  gcloud config get-value project

Activate this training project:
  gcloud config configurations activate "$TREDENCE_GCLOUD_CONFIG" 2>/dev/null || true
  gcloud config set project "$GOOGLE_CLOUD_PROJECT"
  gcloud auth application-default set-quota-project "$GOOGLE_CLOUD_PROJECT"

EOF
