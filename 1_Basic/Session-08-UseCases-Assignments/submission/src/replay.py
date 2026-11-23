"""Record and replay for the search runtime: test without calling Google Cloud.

While the services work, record real responses once:
    MEDEVIDENCE_RECORD=1 python src/rag_runtime.py "..." --mode current --country Germany

Later, replay them with no network, no cost and no 429s:
    MEDEVIDENCE_OFFLINE=1 pytest tests/

Recordings live in tests/fixtures/runtime/, one JSON file per call, keyed by
the call's name and its inputs (never by timestamps, so a replay a week later
finds the same file). In offline mode the runtime refuses to create any Google
client, so a passing offline test proves that nothing reached the cloud.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from config import ROOT


FIXTURES = ROOT / "tests" / "fixtures" / "runtime"


def offline() -> bool:
    return os.getenv("MEDEVIDENCE_OFFLINE") == "1"


def recording() -> bool:
    return os.getenv("MEDEVIDENCE_RECORD") == "1"


def _encode(obj):
    """JSON-safe copy: datetimes become {"__dt__": iso}."""
    if isinstance(obj, datetime):
        return {"__dt__": obj.isoformat()}
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_encode(v) for v in obj]
    return obj


def _decode(obj):
    """Reverse of _encode."""
    if isinstance(obj, dict):
        if set(obj) == {"__dt__"}:
            return datetime.fromisoformat(obj["__dt__"])
        return {k: _decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode(v) for v in obj]
    return obj


def _path(name: str, parts: dict):
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return FIXTURES / f"{name}-{digest}.json"


def call(name: str, parts: dict, fn):
    """Run fn() (online), save its result when recording, or replay it when offline."""
    path = _path(name, parts)
    if offline():
        if not path.exists():
            raise RuntimeError(f"Offline: no recording for '{name}' with {parts}. "
                               "Run it once online with MEDEVIDENCE_RECORD=1.")
        return _decode(json.loads(path.read_text(encoding="utf-8"))["result"])
    result = fn()
    if recording():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": name, "parts": parts, "result": _encode(result)},
                                   indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return result
