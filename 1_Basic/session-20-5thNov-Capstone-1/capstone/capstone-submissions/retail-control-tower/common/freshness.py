"""Freshness rules, decided by code (Gate 1).

Every result carries its source time (when the source says the fact was true:
snapshot time, extraction time, event time). Anything older than its source's
allowed age is "stale": shown as stale, never used as current evidence.

The model never does this arithmetic. Tools return ages and hour counts that
were worked out here, so "the snapshot is 2 days old" is a fact, not a guess.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC (BigQuery TIMESTAMP comes back aware, CSV parsing may not)."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def age_minutes(source_time: datetime | None, now: datetime) -> int | None:
    if source_time is None:
        return None
    return int((utc(now) - utc(source_time)).total_seconds() // 60)


def freshness(source_time: datetime | None, max_age_minutes: int, now: datetime) -> str:
    """'fresh' or 'stale'. No source time means freshness can't be proven, so it is stale.

    A source time in the future (clock skew, bad load) is also stale: it can't be trusted.
    """
    age = age_minutes(source_time, now)
    if age is None or age < -1 or age > max_age_minutes:
        return "stale"
    return "fresh"


def hours_between(earlier: datetime | None, later: datetime | None) -> float | None:
    if earlier is None or later is None:
        return None
    return round((utc(later) - utc(earlier)).total_seconds() / 3600, 1)


def hours_ago(when: datetime | None, now: datetime) -> float | None:
    """Positive for the past, negative for the future (e.g. a promise date still ahead)."""
    return hours_between(when, now)
