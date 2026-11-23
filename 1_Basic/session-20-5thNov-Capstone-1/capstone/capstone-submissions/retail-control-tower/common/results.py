"""One result contract for every tool, in both services.

Every tool returns a dict with the same top-level keys, so the agent, the
harness and the evaluation read results the same way, and a tool never raises
a raw exception into the model (session 13 errors.py, extended):

    status        "ok" | "not_found" | "no_evidence" | "error"
    evidence_id   stable ID the answer must cite, e.g. "EV-ORD-ORD-78421-3f9a1c"
    source        where the fact came from, e.g. "bigquery:orders"
    source_time   when the source says the fact was true (UTC) or None
    read_at       when this tool read it (UTC)
    freshness     "fresh" | "stale" | "n/a"   (decided by code, never the model)
    age_minutes   source age at read time, or None
    data          the allowlisted fields only
    error_type / message / retryable   only when status == "error"

`not_found` is evidence too ("there is no such order" is a fact), so it gets
an evidence ID. `no_evidence` means a search ran and found nothing relevant
enough: the caller must abstain, not guess.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from common.freshness import age_minutes, freshness

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# error_type values and whether trying again can help.
ERROR_TYPES = {
    "invalid_argument": False,   # bad input from the model: fix the call, don't retry it
    "timeout": True,
    "unavailable": True,         # dependency down (BigQuery, the specialist)
    "budget": False,             # stopped by the harness
    "policy": False,             # refused by the harness or the tool's own rules
    "internal": False,
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).strftime(TIME_FORMAT)


def evidence_id(kind: str, key: str, source_time: datetime | None = None) -> str:
    """Same fact at the same source time -> same ID, so citations can be checked and repeated.

    Whitespace in the key becomes "_" ("carrier:Blue Dart" -> "carrier:Blue_Dart"): an ID must be one
    unbroken token, or the citation check can't find it in the answer.
    """
    key = re.sub(r"\s+", "_", str(key).strip())
    digest = hashlib.sha256(f"{kind}|{key}|{iso(source_time)}".encode()).hexdigest()[:6]
    return f"EV-{kind}-{key}-{digest}"


def ok(kind: str, key: str, source: str, data: Any, *, source_time: datetime | None = None,
       max_age_minutes: int | None = None, now: datetime | None = None) -> dict:
    now = now or now_utc()
    return {
        "status": "ok",
        "evidence_id": evidence_id(kind, key, source_time),
        "source": source,
        "source_time": iso(source_time),
        "read_at": iso(now),
        "freshness": freshness(source_time, max_age_minutes, now) if max_age_minutes else "n/a",
        "age_minutes": age_minutes(source_time, now),
        "data": data,
    }


def not_found(kind: str, key: str, source: str, message: str, *, now: datetime | None = None) -> dict:
    now = now or now_utc()
    return {
        "status": "not_found",
        "evidence_id": evidence_id(kind, key),
        "source": source,
        "source_time": None,
        "read_at": iso(now),
        "freshness": "n/a",
        "age_minutes": None,
        "data": None,
        "message": message,
    }


def no_evidence(source: str, message: str, data: Any = None) -> dict:
    return {"status": "no_evidence", "evidence_id": None, "source": source, "source_time": None,
            "read_at": iso(now_utc()), "freshness": "n/a", "age_minutes": None, "data": data,
            "message": message}


def error(source: str, error_type: str, message: str) -> dict:
    if error_type not in ERROR_TYPES:
        error_type = "internal"
    return {"status": "error", "evidence_id": None, "source": source, "source_time": None,
            "read_at": iso(now_utc()), "freshness": "n/a", "age_minutes": None, "data": None,
            "error_type": error_type, "message": message, "retryable": ERROR_TYPES[error_type]}


def collect_evidence_ids(value: Any) -> list[str]:
    """Every evidence ID inside a result, including nested ones (e.g. the specialist's inventory read)."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_id" and isinstance(item, str):
                found.append(item)
            elif key == "evidence_ids" and isinstance(item, list):
                found.extend(i for i in item if isinstance(i, str))
            else:
                found.extend(collect_evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(collect_evidence_ids(item))
    return list(dict.fromkeys(found))
