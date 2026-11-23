"""Small file-backed TTL cache (Gate 10), used for query embeddings and retrieval results only.

Keys always include what makes a value valid: the model and dimension for an
embedding; the question, filters, index version and register fingerprint for
retrieval. Order data is not cached (a fresh BigQuery read is quick), and
inventory and final answers are never cached: they are live state.

One JSON file per cache under output/cache/ keeps the demo simple and survives
restarts. Production: Memorystore (Redis) with the same keys and TTLs.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

from common import config


class TTLCache:
    def __init__(self, name: str, ttl_seconds: int, max_entries: int = 2000):
        self.name = name
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._data: dict[str, dict] | None = None
        self.hits = 0
        self.misses = 0

    @property
    def path(self) -> Path:
        return config.CACHE_DIR / f"{self.name}.json"

    @staticmethod
    def key(*parts: Any) -> str:
        """The raw text never sits in the key file: only its hash (questions can contain IDs)."""
        return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()

    def _load(self) -> dict:
        if self._data is None:
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                self._data = {}
        return self._data

    def get(self, key: str) -> Any | None:
        if self.ttl <= 0:
            self.misses += 1
            return None
        with self._lock:
            entry = self._load().get(key)
        if entry is None or time.time() - entry["at"] > self.ttl:
            self.misses += 1
            return None
        self.hits += 1
        return entry["value"]

    def put(self, key: str, value: Any) -> None:
        if self.ttl <= 0:
            return
        with self._lock:
            data = self._load()
            now = time.time()
            data[key] = {"at": now, "value": value}
            for k in [k for k, v in data.items() if now - v["at"] > self.ttl]:
                del data[k]
            while len(data) > self.max_entries:          # oldest first
                del data[min(data, key=lambda k: data[k]["at"])]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self.path)

    def clear(self) -> None:
        with self._lock:
            self._data = {}
            self.path.unlink(missing_ok=True)

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses}
