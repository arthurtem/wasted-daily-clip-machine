"""Adaptive launch-volume limits stored in Postgres."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from clipmachine import db
from clipmachine.config import Settings


@dataclass(frozen=True)
class AutomationLimits:
    """Current daily and per-run automation limits."""

    upload_cap: int
    fetch_limit: int
    render_limit: int


def current_limits(
    settings: Settings, now: datetime | None = None
) -> AutomationLimits:
    """Return the current adaptive caps, ramping by launch day."""
    if not getattr(settings, "automation_enabled", False):
        return AutomationLimits(
            upload_cap=int(getattr(settings, "max_uploads_per_day", 100)),
            fetch_limit=int(getattr(settings, "max_clips_per_run", 20)),
            render_limit=int(getattr(settings, "max_render_per_run", 20)),
        )

    now = now or datetime.now(timezone.utc)
    state = db.ensure_automation_state(
        getattr(settings, "automation_launch_date", "2026-11-19"),
        int(getattr(settings, "automation_start_upload_cap", 75)),
        int(getattr(settings, "automation_fetch_limit", 20)),
        int(getattr(settings, "automation_render_limit", 20)),
    )
    try:
        launch = date.fromisoformat(
            getattr(settings, "automation_launch_date", "2026-11-19")
        )
    except ValueError:
        launch = now.date()
    days = max(0, (now.date() - launch).days)
    desired = min(
        int(getattr(settings, "automation_start_upload_cap", 75))
        + days * int(getattr(settings, "automation_ramp_per_day", 10)),
        int(getattr(settings, "automation_max_upload_cap", 100)),
    )

    recent_limit_error = False
    for key in ("last_upload_limit_at", "last_quota_error_at"):
        value = state.get(key)
        if isinstance(value, datetime) and now - value < timedelta(hours=24):
            recent_limit_error = True
            break

    upload_cap = int(state.get("upload_cap") or desired)
    if not recent_limit_error:
        upload_cap = desired
        db.set_automation_limits(
            upload_cap,
            int(getattr(settings, "automation_fetch_limit", 20)),
            int(getattr(settings, "automation_render_limit", 20)),
        )
    return AutomationLimits(
        upload_cap=upload_cap,
        fetch_limit=int(getattr(settings, "automation_fetch_limit", 20)),
        render_limit=int(getattr(settings, "automation_render_limit", 20)),
    )


def record_upload_limit_error(kind: str) -> None:
    """Record a YouTube upload/quota stop in the automation state."""
    db.record_upload_limit_error(kind)
