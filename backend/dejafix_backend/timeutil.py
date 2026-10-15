"""시각은 전부 UTC ISO 8601 (예: 2026-10-16T01:20:00Z). KST 변환은 프론트가 한다."""

from datetime import datetime, timezone


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_iso() -> str:
    return to_iso(datetime.now(timezone.utc))
