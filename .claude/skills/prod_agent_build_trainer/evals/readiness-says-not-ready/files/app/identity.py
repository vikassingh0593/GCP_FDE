"""Training-only identity helper.

This module intentionally performs identification, not authentication.
The same normalized email deterministically maps to the same ADK user_id.
"""

from __future__ import annotations

import hashlib
import re

from app.config import settings


def normalize_email(email: str) -> str:
    """Normalize and minimally validate an email address for the lab."""
    normalized = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def build_user_id(email: str) -> str:
    """Return a stable, non-email ADK user_id derived from normalized email."""
    normalized = normalize_email(email)
    digest = hashlib.sha256(
        f"{settings.identity_salt}:{normalized}".encode("utf-8")
    ).hexdigest()[:20]
    return f"user_{digest}"
