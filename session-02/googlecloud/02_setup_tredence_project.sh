#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/training.env"

echo "======================================================================"
echo " TREDENCE FDE — DEDICATED GOOGLE CLOUD SETUP"
echo "======================================================================"
echo "Configuration : $TREDENCE_GCLOUD_CONFIG"
echo "PROJECT ID    : $GOOGLE_CLOUD_PROJECT"
echo "Location      : $GOOGLE_CLOUD_LOCATION"

command -v gcloud >/dev/null 2>&1 || { echo "Install gcloud: https://cloud.google.com/sdk/docs/install"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 not found"; exit 1; }

echo; echo "[1/8] Current state BEFORE changes"
gcloud config configurations list --filter="is_active:true" --format="table(name,is_active)"
echo "Current project: $(gcloud config get-value project 2>/dev/null || true)"

echo; echo "[2/8] Dedicated gcloud configuration"
if gcloud config configurations describe "$TREDENCE_GCLOUD_CONFIG" >/dev/null 2>&1; then
  gcloud config configurations activate "$TREDENCE_GCLOUD_CONFIG"
else
  gcloud config configurations create "$TREDENCE_GCLOUD_CONFIG"
fi

echo; echo "[3/8] CLI authentication"
if ! gcloud auth print-access-token >/dev/null 2>&1; then gcloud auth login; fi
gcloud auth list --filter=status:ACTIVE --format="table(account,status)"

echo; echo "[4/8] Validate exact PROJECT ID"
if ! gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format="value(projectId)" >/dev/null 2>&1; then
  echo "ERROR: '$GOOGLE_CLOUD_PROJECT' is not an accessible exact projectId."
  echo "Accessible projects:"
  gcloud projects list --format="table(projectId,name)" || true
  echo "Edit training.env with the exact projectId and retry."; exit 1
fi
ACTUAL="$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format='value(projectId)')"
NAME="$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format='value(name)')"
echo "Validated projectId: $ACTUAL"
echo "Display name       : $NAME"
gcloud config set project "$ACTUAL"
gcloud config set billing/quota_project "$ACTUAL" || true

echo; echo "[5/8] Application Default Credentials (ADC)"
if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  gcloud auth application-default login
else
  echo "ADC already exists."
fi
echo "Setting ADC quota project to $ACTUAL..."
if ! gcloud auth application-default set-quota-project "$ACTUAL"; then
  echo "ERROR: Could not set ADC quota project."
  echo "Likely missing serviceusage.services.use."
  echo "Ask admin for roles/serviceusage.serviceUsageConsumer."; exit 1
fi

echo; echo "[6/8] Vertex AI API"
if gcloud services list --enabled --project="$ACTUAL" \
   --filter="name:aiplatform.googleapis.com" --format="value(name)" | grep -q aiplatform.googleapis.com; then
  echo "aiplatform.googleapis.com: ENABLED"
else
  echo "Vertex AI API not enabled; attempting enable..."
  gcloud services enable aiplatform.googleapis.com --project="$ACTUAL" || {
    echo "ERROR: Ask project admin to enable aiplatform.googleapis.com"; exit 1; }
fi

echo; echo "[7/8] Python environments + lab .env"
for LAB in lab02_prompt_structure_structured_output lab03_prompt_reliability; do
  D="$ROOT/$LAB"
  rm -rf "$D/.venv" "$D/venv"
  python3 -m venv "$D/venv"
  "$D/venv/bin/python" -m pip install --upgrade pip
  "$D/venv/bin/pip" install -r "$D/requirements.txt"
  cat > "$D/.env" <<EOF
GOOGLE_CLOUD_PROJECT=$ACTUAL
GOOGLE_CLOUD_LOCATION=$GOOGLE_CLOUD_LOCATION
GOOGLE_CLOUD_QUOTA_PROJECT=$ACTUAL
GOOGLE_GENAI_USE_VERTEXAI=TRUE
MODEL_ID=$MODEL_ID
EOF
  chmod +x "$D/run.sh"
done

echo; echo "[8/8] REAL Vertex AI preflight"
"$ROOT/lab02_prompt_structure_structured_output/venv/bin/python" "$ROOT/vertex_preflight.py"

echo
echo "======================================================================"
echo " READY"
echo "======================================================================"
echo "Active config : $(gcloud config configurations list --filter='is_active:true' --format='value(name)')"
echo "Project       : $(gcloud config get-value project 2>/dev/null)"
echo "Location      : $GOOGLE_CLOUD_LOCATION"
echo "Run Lab 02   : cd lab02_prompt_structure_structured_output && ./run.sh"
