
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from .errors import failure, success


DATA = Path(__file__).resolve().parents[2] / "data"


def _load(name: str) -> Any:
    """Load one deterministic enterprise fixture."""
    with (DATA / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)

def get_incident(incident_id: str) -> dict[str, Any]:
    """Retrieve authoritative metadata for one exact incident ID.

    Use for incident severity, status, symptoms and suspected services.
    Read-only.
    """
    item = _load("incidents.json").get(incident_id.upper())

    if item is None:
        return failure(
            "NOT_FOUND",
            f"Incident {incident_id} was not found.",
        )

    return success(item)





def get_service_metrics(service_name: str) -> dict[str, Any]:
    """Retrieve current incident-window telemetry for one exact service.

    Use to verify latency, error-rate and dominant-error evidence. Read-only.
    """
    if os.getenv(
        "SIMULATE_TELEMETRY_FAILURE",
        "false",
    ).lower() in {"1", "true", "yes", "on"}:
        return failure(
            "DEPENDENCY_UNAVAILABLE",
            "Telemetry backend is temporarily unavailable.",
            retryable=True,
        )

    service = service_name.lower()
    item = _load("metrics.json").get(service)

    if item is None:
        return failure(
            "NOT_FOUND",
            f"No telemetry exists for service {service_name}.",
        )

    return success({"service_name": service, **item})



def get_recent_deployments(service_name: str) -> dict[str, Any]:
    """Retrieve recent deployments for one exact service.

    Use to test a deployment hypothesis. Temporal correlation is not proof of
    causality. Read-only.
    """
    service = service_name.lower()
    items = _load("deployments.json").get(service)

    if items is None:
        return failure(
            "NOT_FOUND",
            f"No deployment history exists for service {service_name}.",
        )

    return success(
        {
            "service_name": service,
            "deployments": items,
        }
    )




def search_historical_incidents(query: str) -> dict[str, Any]:
    """Search historical incident summaries for hypothesis generation.

    Historical root causes are supporting evidence only; verify them against
    current incident telemetry and deployment evidence.
    """
    terms = {
        token.lower()
        for token in query.split()
        if len(token) >= 4
    }

    results = []

    for item in _load("history.json"):
        text = " ".join(str(v) for v in item.values()).lower()
        score = sum(1 for term in terms if term in text)
        results.append({**item, "match_score": score})

    results.sort(
        key=lambda item: item["match_score"],
        reverse=True,
    )

    return success({"query": query, "results": results})
