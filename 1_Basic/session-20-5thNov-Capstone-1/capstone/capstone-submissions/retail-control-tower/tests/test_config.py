"""common/config.py: required values fail loudly, bad values are named, the salt never leaks."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from conftest import ROOT, TEST_ENV


def _import_config(**overrides: str | None) -> subprocess.CompletedProcess:
    """Import config in a fresh process with a controlled environment (it reads env at import)."""
    env = {k: v for k, v in os.environ.items()}
    env.update(TEST_ENV)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run([sys.executable, "-c", "from common import config"],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def test_loads_and_builds_ids():
    from common import config

    assert config.table_id("orders") == f"{config.PROJECT_ID}.{config.BQ_DATASET}.orders"
    assert set(config.OPERATIONAL_TABLES) == {"orders", "inventory", "carrier_events", "warehouse_events", "change_log"}
    doc = config.DOCS_DIR / "runbooks" / "rb-car-003-carrier-delay.md"
    assert config.gcs_doc_path(doc) == f"{config.GCS_DOCS_PREFIX}/runbooks/rb-car-003-carrier-delay.md"


def test_paths_are_inside_the_project():
    from common import config

    for path in (config.TABLES_DIR, config.SCHEMAS_DIR, config.DOCS_DIR, config.SESSION_DB_FILE):
        assert path.is_relative_to(config.ROOT), path
    # OUTPUT_DIR is a temp folder under the tests (conftest); everything written at runtime sits under it.
    for path in (config.LOGS_DIR, config.TRACES_DIR, config.CACHE_DIR, config.PARSED_DIR, config.EVAL_DIR):
        assert path.is_relative_to(config.OUTPUT_DIR), path


def test_missing_required_value_fails_and_names_it():
    for name in ("GOOGLE_CLOUD_PROJECT", "GCS_BUCKET", "BQ_DATASET", "IDENTITY_SALT"):
        result = _import_config(**{name: None})
        assert result.returncode != 0
        assert name in result.stderr


def test_bad_number_is_named():
    result = _import_config(TOP_K="twenty")
    assert result.returncode != 0 and "TOP_K" in result.stderr


def test_related_values_are_checked():
    assert "TOP_N" in _import_config(TOP_N="30", TOP_K="20").stderr
    assert "EMBEDDING_DIMENSION" in _import_config(EMBEDDING_DIMENSION="1000").stderr
    assert "FULFILMENT_TIMEOUT_SECONDS" in _import_config(FULFILMENT_TIMEOUT_SECONDS="90",
                                                          MAX_INVOCATION_SECONDS="60").stderr
    assert "IDENTITY_SALT" in _import_config(IDENTITY_SALT="replace-with-any-random-string").stderr


def test_document_ai_settings_are_read_and_checked():
    from common import config

    assert config.DOCUMENT_AI_LOCATION in ("us", "eu")
    assert config.DOCUMENT_AI_PROCESSOR_ID_FILE.is_relative_to(config.ROOT)
    assert isinstance(config.INCLUDE_ANCESTOR_HEADINGS, bool)
    assert "DOCUMENT_AI_LOCATION" in _import_config(DOCUMENT_AI_LOCATION="us-central1").stderr
    assert "INCLUDE_ANCESTOR_HEADINGS" in _import_config(INCLUDE_ANCESTOR_HEADINGS="maybe").stderr
    assert "DOCUMENT_AI_PROCESSOR_VERSION" in _import_config(DOCUMENT_AI_PROCESSOR_VERSION="latest").stderr


def test_summary_never_contains_the_salt():
    from common import config

    assert config.IDENTITY_SALT not in json.dumps(config.summary())


def test_demo_freshness_window_keeps_scenarios_correct():
    """S7's stale snapshot (2 days) must stay stale, and fresh rows must survive a test session."""
    from common import config

    assert 60 <= config.INVENTORY_MAX_AGE_MINUTES < 2 * 24 * 60
    assert 60 <= config.ORDER_MAX_AGE_MINUTES < 2 * 24 * 60
