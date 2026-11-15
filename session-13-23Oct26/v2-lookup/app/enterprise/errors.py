"""Structured enterprise error helpers."""

from __future__ import annotations

from typing import Any


def success(data: Any) -> dict[str, Any]:
    """Return the common successful operation contract."""
    return {
        "status": "success",
        "code": "OK",
        "data": data,
        "retryable": False,
    }


def failure(
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    """Return the common failed operation contract."""
    return {
        "status": "error",
        "code": code,
        "message": message,
        "retryable": retryable,
    }
