"""Tests for upload window and pacing calculations."""

from __future__ import annotations

from datetime import datetime, timezone

from clipmachine.upload_policy import (
    UploadPolicy,
    day_start,
    inside_window,
    next_allowed_upload,
    next_window_start,
)

POLICY = UploadPolicy(
    max_uploads_per_day=25,
    window_start="13:00",
    window_end="05:00",
    timezone_name="Europe/Brussels",
    min_minutes_between_uploads=30,
)


def test_window_wraps_past_midnight() -> None:
    """Hours in the evening and early morning are inside the window."""
    assert inside_window(datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc), POLICY)
    assert inside_window(datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc), POLICY)
    assert not inside_window(
        datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc), POLICY
    )


def test_next_window_start_moves_to_brussels_afternoon() -> None:
    """An early-morning close returns the same day's 13:00 start."""
    result = next_window_start(
        datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc), POLICY
    )
    assert result.astimezone(timezone.utc) == datetime(
        2026, 11, 16, 12, 0, tzinfo=timezone.utc
    )


def test_day_start_uses_brussels_midnight() -> None:
    """The day starts at local midnight, not UTC midnight."""
    result = day_start(datetime(2026, 11, 16, 12, 5, tzinfo=timezone.utc), POLICY)

    assert result == datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc)


def test_next_allowed_respects_gap_and_slot() -> None:
    """The minimum gap is rounded to the next quarter-hour slot."""
    result = next_allowed_upload(
        datetime(2026, 11, 16, 12, 5, tzinfo=timezone.utc),
        policy=POLICY,
        latest_upload=datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc),
        uploaded_today=0,
    )
    assert result.astimezone(timezone.utc) == datetime(
        2026, 11, 16, 12, 30, tzinfo=timezone.utc
    )


def test_next_allowed_waits_for_local_midnight() -> None:
    """A full day's quota resets at the next local midnight."""
    result = next_allowed_upload(
        datetime(2026, 11, 16, 12, 5, tzinfo=timezone.utc),
        policy=POLICY,
        latest_upload=datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc),
        uploaded_today=25,
    )
    assert result.astimezone(timezone.utc) == datetime(
        2026, 11, 16, 23, 0, tzinfo=timezone.utc
    )
