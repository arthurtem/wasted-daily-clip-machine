"""Upload pacing policy: posting window, rolling cap, and next slot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class UploadPolicy:
    """The launch-week upload cadence."""

    max_uploads_per_day: int
    window_start: str
    window_end: str
    timezone_name: str
    min_minutes_between_uploads: int
    slot_minutes: int = 15


def _clock(value: str) -> time:
    """Parse an HH:MM setting into a time."""
    hour, minute = (int(part) for part in value.split(":"))
    return time(hour=hour, minute=minute)


def policy_from_settings(settings: object) -> UploadPolicy:
    """Build an UploadPolicy from a Settings-like object."""
    return UploadPolicy(
        max_uploads_per_day=int(
            getattr(settings, "max_uploads_per_day", 25)
        ),
        window_start=str(getattr(settings, "upload_window_start", "13:00")),
        window_end=str(getattr(settings, "upload_window_end", "05:00")),
        timezone_name=str(
            getattr(settings, "upload_timezone", "Europe/Brussels")
        ),
        min_minutes_between_uploads=int(
            getattr(settings, "min_minutes_between_uploads", 30)
        ),
    )


def local_now(now: datetime, policy: UploadPolicy) -> datetime:
    """Convert an instant into the policy timezone."""
    zone = ZoneInfo(policy.timezone_name)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(zone)


def inside_window(now: datetime, policy: UploadPolicy) -> bool:
    """Return whether a local instant is inside the (possibly wrapping) window."""
    local = local_now(now, policy)
    start = _clock(policy.window_start)
    end = _clock(policy.window_end)
    current = local.time().replace(tzinfo=None)
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def next_window_start(now: datetime, policy: UploadPolicy) -> datetime:
    """Return the next local window start at or after now."""
    local = local_now(now, policy)
    if inside_window(now, policy):
        return local
    start = _clock(policy.window_start)
    candidate = local.replace(
        hour=start.hour, minute=start.minute, second=0, microsecond=0
    )
    if candidate < local:
        candidate += timedelta(days=1)
    return candidate


def _round_to_slot(value: datetime, slot_minutes: int) -> datetime:
    """Round a local time up to the next upload slot."""
    value = value.replace(second=0, microsecond=0)
    remainder = value.minute % slot_minutes
    if remainder:
        value += timedelta(minutes=slot_minutes - remainder)
    return value


def next_allowed_upload(
    now: datetime,
    *,
    policy: UploadPolicy,
    latest_upload: datetime | None,
    oldest_upload: datetime | None,
    uploaded_last_24h: int,
) -> datetime:
    """Return the next instant the uploader may run."""
    candidate = now
    if latest_upload is not None:
        gap = timedelta(minutes=policy.min_minutes_between_uploads)
        candidate = max(candidate, latest_upload + gap)
    if uploaded_last_24h >= policy.max_uploads_per_day and oldest_upload:
        candidate = max(candidate, oldest_upload + timedelta(hours=24))
    if not inside_window(candidate, policy):
        candidate = next_window_start(candidate, policy)
    return _round_to_slot(candidate, policy.slot_minutes)
