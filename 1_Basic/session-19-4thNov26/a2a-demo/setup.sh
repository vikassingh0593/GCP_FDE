#!/usr/bin/env bash
set -euo pipefail
echo "============================================================"
echo " Tredence FDE — M6 Topic 21 — ADK + A2A Setup"
echo "============================================================"
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
source lab.env
python preflight.py
PYTHONPATH=01_fulfilment_specialist python -m pytest -q 01_fulfilment_specialist/tests
echo
echo "SETUP COMPLETE — now follow instructions.md"
