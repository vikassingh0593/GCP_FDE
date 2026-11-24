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


# -----------------------------------------------------------------------------
# Signed analyst token: every API call after sign-in proves who is calling
# -----------------------------------------------------------------------------
# The analyst ID is not a secret (it appears in logs, traces and escalation rows), so the API must
# never trust an ID sent in a request. Sign-in returns a token signed with IDENTITY_SALT; every other
# endpoint takes the analyst from the token. Still training identity (the email isn't verified), but
# knowing someone's analyst ID no longer opens their sessions.

TOKEN_TTL_SECONDS = 12 * 3600


def issue_token(user_id: str, now: float | None = None) -> str:
    import hashlib
    import hmac
    import time

    expires = int((now or time.time()) + TOKEN_TTL_SECONDS)
    payload = f"{user_id}.{expires}"
    signature = hmac.new(config.IDENTITY_SALT.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{signature}"


def verify_token(token: str | None, now: float | None = None) -> str | None:
    """The analyst ID in a valid, unexpired token; None otherwise."""
    import hashlib
    import hmac
    import time

    try:
        user_id, expires, signature = (token or "").rsplit(".", 2)
        expected = hmac.new(config.IDENTITY_SALT.encode(), f"{user_id}.{expires}".encode(),
                            hashlib.sha256).hexdigest()[:32]
        if hmac.compare_digest(signature, expected) and int(expires) > (now or time.time()):
            return user_id
    except ValueError:
        pass
    return None
