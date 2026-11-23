#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "== Topic 22: Official A2UI + ADK =="
"${PYTHON_BIN}" --version

if [[ ! -d .venv ]]; then
  "${PYTHON_BIN}" -m venv .venv
fi

.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r backend/requirements.txt

if [[ ! -f lab.env ]]; then
  cp lab.env.example lab.env
fi

echo
echo "Python setup complete."
echo "Frontend dependencies are installed separately:"
echo "  cd frontend && npm install"
echo
echo "Next:"
echo "  source .venv/bin/activate"
echo "  source lab.env"
echo "  python preflight.py"
echo "  pytest -q"
