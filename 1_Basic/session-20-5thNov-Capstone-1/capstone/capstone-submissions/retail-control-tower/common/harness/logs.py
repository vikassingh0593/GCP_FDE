"""Structured, masked JSON-line logging, one file per service under output/logs/.

Every row carries the correlation ID, so one request can be followed from the
web app through the orchestrator, over A2A, to the specialist's tool:

    grep corr-3f9a1c2b7d4e output/logs/*.jsonl

Values are masked before they are written. Warnings and errors also go to
stderr, so they show in the terminal running the service.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from common import config
from common.masking import mask

_lock = threading.Lock()


def _append(path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, default=str, ensure_ascii=False)
    with _lock, open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def log_event(service: str, event: str, *, correlation_id: str | None, level: str = "INFO", **fields: Any) -> None:
    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "level": level,
           "service": service, "event": event, "correlation_id": correlation_id, **mask(fields)}
    _append(config.LOGS_DIR / f"{service}.jsonl", row)
    if level in ("WARNING", "ERROR"):
        print(json.dumps(row, default=str), file=sys.stderr, flush=True)


def write_trace(service: str, row: dict) -> None:
    _append(config.TRACES_DIR / f"{service}.jsonl", row)


def configure_stdlib_logging(level: int = logging.INFO) -> None:
    """Library warnings to stderr; our own rows go through log_event."""
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("google_genai", "google_adk", "httpx", "urllib3", "google.auth", "a2a"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
