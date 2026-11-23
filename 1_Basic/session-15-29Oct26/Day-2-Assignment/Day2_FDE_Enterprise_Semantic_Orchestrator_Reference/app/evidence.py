"""Evidence provenance model used by the orchestration loop."""

from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    evidence_id: str
    source_action: str
    source_system: str
    observed_at: str
    source_timestamp: str | None = None
    status: str
    freshness_seconds: float | None = None
    payload: dict = Field(default_factory=dict)


class EvidenceRegister:
    def __init__(self) -> None:
        self._items: list[Evidence] = []

    @property
    def items(self) -> list[Evidence]:
        return list(self._items)

    def add(
        self,
        source_action: str,
        source_system: str,
        status: str,
        payload: dict,
        source_timestamp: str | None = None,
    ) -> Evidence:
        now = datetime.now(timezone.utc)
        freshness = None
        if source_timestamp:
            try:
                stamp = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
                freshness = max(0.0, (now - stamp).total_seconds())
            except ValueError:
                freshness = None

        item = Evidence(
            evidence_id=f"EV-{len(self._items)+1:03d}",
            source_action=source_action,
            source_system=source_system,
            observed_at=now.isoformat(),
            source_timestamp=source_timestamp,
            status=status,
            freshness_seconds=freshness,
            payload=payload,
        )
        self._items.append(item)
        return item

    def action_count(self, action: str) -> int:
        return sum(1 for item in self._items if item.source_action == action)

    def successful_actions(self) -> set[str]:
        return {item.source_action for item in self._items if item.status == "SUCCESS"}

    def prompt_view(self) -> list[dict]:
        return [item.model_dump() for item in self._items]
