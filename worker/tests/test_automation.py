"""Tests for adaptive automation caps."""

from __future__ import annotations

from datetime import datetime, timezone

from clipmachine.automation import current_limits
from clipmachine.config import Settings


def settings(**overrides: object) -> Settings:
    values = dict(
        game_name="Grand Theft Auto VI",
        lookback_hours=24,
        min_views=150,
        max_clips_per_run=10,
        max_clip_seconds=60,
        uploads_per_run=1,
        automation_enabled=False,
    )
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_automation_disabled_uses_static_limits() -> None:
    limits = current_limits(settings(max_uploads_per_day=25))
    assert limits.upload_cap == 25
    assert limits.fetch_limit == 10


def test_ramp_uses_launch_day(monkeypatch) -> None:
    import clipmachine.automation as automation

    called = {}
    monkeypatch.setattr(
        automation.db,
        "ensure_automation_state",
        lambda *args: {
            "upload_cap": 75,
            "last_upload_limit_at": None,
            "last_quota_error_at": None,
        },
    )
    monkeypatch.setattr(
        automation.db,
        "set_automation_limits",
        lambda *args: called.setdefault("limits", args),
    )
    config = settings(
        automation_enabled=True,
        automation_launch_date="2026-11-19",
        automation_start_upload_cap=75,
        automation_ramp_per_day=10,
        automation_max_upload_cap=100,
        automation_fetch_limit=20,
        automation_render_limit=20,
    )
    limits = current_limits(
        config, datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
    )
    assert limits.upload_cap == 95
    assert limits.fetch_limit == 20
    assert limits.render_limit == 20
    assert called["limits"] == (95, 20, 20)
