"""Small helpers shared by the scripts in scripts/ (load_data, ingest_docs, ...).

For scripts run by hand only. log() prints to the terminal and fail() stops the
process with SystemExit: right for a script, wrong for a running service. The
web app and the agents must not use these; they log through the harness and
return errors instead of exiting.
"""

from __future__ import annotations

from datetime import datetime, timezone

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"      # the UTC format used in data/tables and manifest.json


def log(tag: str, message: str) -> None:
    """One aligned progress line, e.g. "[load   ] orders: 24 rows"."""
    print(f"[{tag:<7}] {message}", flush=True)


def fail(message: str) -> None:
    """Stop the script with a clear reason (exit code 1)."""
    raise SystemExit(f"\nFAILED: {message}")


def parse_utc(value: str) -> datetime:
    """'2026-11-22T12:33:00Z' -> timezone-aware UTC datetime."""
    return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=timezone.utc)
