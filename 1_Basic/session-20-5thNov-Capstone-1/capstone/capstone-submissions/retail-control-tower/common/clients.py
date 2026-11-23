"""Cloud clients, created once per process and reused, plus retry for transient errors.

Nothing here runs at import: clients are built on first use, so importing a
module never needs credentials. Under the offline tests (RCT_OFFLINE=1, set
by tests/conftest.py) building a client fails loudly, so a test can never
reach the cloud by accident (session 8 _no_cloud_offline pattern).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, TypeVar

from common import config

T = TypeVar("T")
_lock = threading.Lock()
_clients: dict[str, object] = {}
log = logging.getLogger("clients")

# Busy (429/503) and dropped connections are retried; anything else surfaces at once.
TRANSIENT = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "ServiceUnavailable", "TooManyRequests",
             "DEADLINE_EXCEEDED", "ConnectionError", "RemoteDisconnected", "ConnectionResetError")


def is_transient(exc: BaseException) -> bool:
    return any(s in f"{type(exc).__name__} {exc}" for s in TRANSIENT)


def with_retry(call: Callable[[], T], what: str, attempts: int = 4) -> T:
    """Retry with backoff 2, 4, 8 s on transient errors only (session 8 with_retry)."""
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - classified below
            if not is_transient(exc) or attempt == attempts - 1:
                raise
            wait = 2 ** (attempt + 1)
            log.warning("retry %s after %s: waiting %ss", what, type(exc).__name__, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _get(name: str, factory: Callable[[], object]):
    if os.getenv("RCT_OFFLINE") == "1":
        raise RuntimeError(f"offline test tried to create a {name} client; use a fake")
    with _lock:
        if name not in _clients:
            _clients[name] = factory()
        return _clients[name]


def bigquery_client():
    # Short-query mode: small read queries run without creating a job when BigQuery allows it,
    # which cuts ~1-1.5 s of job overhead from every tool call (measured on the first GCP run).
    from google.cloud import bigquery
    return _get("bigquery", lambda: bigquery.Client(project=config.PROJECT_ID, location=config.BIGQUERY_LOCATION,
                                                    default_job_creation_mode="JOB_CREATION_OPTIONAL"))


def storage_client():
    from google.cloud import storage
    return _get("storage", lambda: storage.Client(project=config.PROJECT_ID))


def genai_client(location: str):
    from google import genai
    return _get(f"genai:{location}", lambda: genai.Client(vertexai=True, project=config.PROJECT_ID,
                                                          location=location))


def rank_client():
    from google.cloud import discoveryengine_v1 as discoveryengine
    return _get("rank", discoveryengine.RankServiceClient)


def query_rows(sql: str, params: list | None = None, what: str = "bigquery", timeout: float = 30.0) -> list[dict]:
    """Run a parameterized, read-only BigQuery query and return plain dict rows.

    use_query_cache=False: BigQuery's own result cache would hand back old rows
    after a reload, which is exactly the staleness the freshness rules exist to catch.
    """
    from google.cloud import bigquery
    job_config = bigquery.QueryJobConfig(query_parameters=params or [], use_query_cache=False)
    rows = with_retry(lambda: list(bigquery_client().query_and_wait(sql, job_config=job_config,
                                                                    wait_timeout=timeout)), what)
    return [dict(r.items()) for r in rows]
