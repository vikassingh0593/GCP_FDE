from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class RequestContext:
    """Trusted metadata attached to one enterprise request."""

    correlation_id: str
    tenant_id: str
    user_id: str
    environment: str
    received_at: str


def create_request_context() -> RequestContext:
    """Create fresh trusted metadata for a new user invocation."""
    return RequestContext(
        correlation_id=f"corr-{uuid.uuid4().hex[:10]}",
        tenant_id=os.getenv("LAB_TENANT_ID", "tenant-retail-a"),
        user_id=os.getenv("LAB_USER_ID", "fde-user-101"),
        environment=os.getenv("LAB_ENVIRONMENT", "training"),
        received_at=datetime.now(timezone.utc).isoformat(),
    )