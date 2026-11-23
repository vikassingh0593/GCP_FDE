"""Mask sensitive values before anything is logged or traced.

Masking happens before the log call, never after: a log line can't be recalled.
The orders table is the only place customer details exist (Gate 1), and the
tools don't return them to the model at all; this is the second line of
defence for anything that reaches a log, a trace or a session view.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

# Keys that are sensitive wherever they appear (tool args, results, session state).
SENSITIVE_KEYS = {"customer_name", "customer_phone", "shipping_address", "payment_status",
                  "email", "phone", "address", "full_name", "analyst_name", "password", "token",
                  "user:email", "user:full_name"}

# Not inside a longer word: "call_1234567890" (an ADK function-call ID) is not a phone number.
_PHONE = re.compile(r"(?<![\w])\+?\d[\d\s-]{8,}\d(?![\w])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def mask_text(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    return _PHONE.sub("[phone]", text)


def mask(value: Any, *, max_text: int = 300) -> Any:
    """Recursively mask a value for logging: sensitive keys hidden, phones and emails redacted, long text cut."""
    if isinstance(value, dict):
        return {k: ("[masked]" if str(k).lower() in SENSITIVE_KEYS else mask(v, max_text=max_text))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask(v, max_text=max_text) for v in list(value)[:50]]
    if isinstance(value, str):
        text = mask_text(value)
        return text if len(text) <= max_text else text[:max_text] + "…"
    return value


def pseudonymize(value: str, salt: str) -> str:
    """Stable, non-reversible ID for a person. Logs and traces carry this, never the name or email."""
    return hmac.new(salt.encode(), value.strip().lower().encode(), hashlib.sha256).hexdigest()[:12]
