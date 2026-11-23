"""Training-only identity (session 17 identity.py).

This identifies an analyst; it does not authenticate them. The same email
always maps to the same pseudonymous user ID (salted hash), so sessions are
per analyst, and logs and traces never carry the email or the name.
Production: sign-in through IAP or the company identity provider, and the
user ID comes from the verified token instead.
"""

from __future__ import annotations

import re

from common import config
from common.masking import pseudonymize


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def build_user_id(email: str) -> str:
    return f"analyst_{pseudonymize(normalize_email(email), config.IDENTITY_SALT)}"
