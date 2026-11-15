#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# Tredence FDE — M6 Topic 20
# Creates the local Python environment and installs the lab dependencies.
# Run from the repository root: bash setup.sh
# -----------------------------------------------------------------------------

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: python3 was not found. Install Python 3.11+ and retry."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[1/4] Creating .venv ..."
  "$PYTHON_BIN" -m venv .venv
else
  echo "[1/4] Reusing existing .venv ..."
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[2/4] Upgrading pip ..."
python -m pip install --upgrade pip

echo "[3/4] Installing requirements ..."
python -m pip install -r requirements.txt

echo "[4/4] Running deterministic tests ..."
python -m pytest -q

cat <<'EOF'

Setup complete.

NEXT:
  source .venv/bin/activate
  source lab.env
  python preflight.py

Then use TWO terminals:

  Terminal 1 — MCP capability server
    source .venv/bin/activate
    source lab.env
    python -m mcp_server.server

  Terminal 2 — ADK web UI
    source .venv/bin/activate
    source lab.env
    adk web

Read instructions.md for the complete participant sequence.
EOF
