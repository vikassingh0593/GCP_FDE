"""Shared test setup. Every test here is offline: no GCP login, no network.

Run from retail-control-tower/:   python -m pytest -q tests

common.config reads its required settings at import, so they are set here
before any test imports it. If lab.env is sourced, its values win (setdefault);
either way no test calls the cloud.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_ENV = {
    "GOOGLE_CLOUD_PROJECT": "test-project",
    "GCS_BUCKET": "test-bucket",
    "BQ_DATASET": "test_dataset",
    "IDENTITY_SALT": "test-salt-not-secret",
}
for key, value in TEST_ENV.items():
    os.environ.setdefault(key, value)

# Logs, traces and caches written during tests go to a throwaway folder, never
# to the real output/ (forced, even when lab.env is sourced).
os.environ["OUTPUT_DIR"] = tempfile.mkdtemp(prefix="rct-tests-")
# Guard: the cloud clients refuse to start inside tests (see common/clients.py).
os.environ["RCT_OFFLINE"] = "1"


def load_generate_data():
    """data/generate_data.py is a script, not a package: load it by path."""
    spec = importlib.util.spec_from_file_location("generate_data", ROOT / "data" / "generate_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
