"""Timezone-safe datetime helpers (MySQL may return naive UTC datetimes)."""

from __future__ import annotations

from datetime import datetime, timezone


def ensure_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def duration_ms(started_at: datetime, finished_at: datetime) -> int:
    start = ensure_utc_aware(started_at)
    end = ensure_utc_aware(finished_at)
    return max(0, int((end - start).total_seconds() * 1000))
