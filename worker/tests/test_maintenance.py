"""Tests for stale clip expiry."""

from __future__ import annotations

import pytest

from clipmachine import maintenance


def test_expire_stale_deletes_blobs_and_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stale approved/rendered clips are rejected and blobs deleted."""
    clip = {
        "id": "old",
        "status": "approved",
        "blob_url": "https://blob/old.mp4",
        "thumb_url": "https://blob/old.jpg",
    }
    deleted: list[str] = []
    marked: list[tuple[str, bool]] = []
    monkeypatch.setattr(maintenance.db, "get_stale_clips", lambda hours: [clip])
    monkeypatch.setattr(
        maintenance.db, "get_stale_rejected_with_blobs", lambda: []
    )
    monkeypatch.setattr(
        maintenance.blob, "delete_url", lambda url: deleted.append(url)
    )
    monkeypatch.setattr(
        maintenance.db,
        "mark_stale",
        lambda clip_id, clear_blobs=True: marked.append((clip_id, clear_blobs)),
    )

    assert maintenance.expire_stale(36) == 1
    assert deleted == [clip["blob_url"], clip["thumb_url"]]
    assert marked == [("old", True)]


def test_check_upload_statuses_pauses_after_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected upload is marked rejected and pauses automation."""
    clip = {"id": "abc", "youtube_video_id": "vid1", "streamer_login": "xqc"}
    monkeypatch.setattr(
        maintenance.db, "get_recent_uploads", lambda since, limit=50: [clip]
    )
    monkeypatch.setattr(
        "clipmachine.youtube.get_video_statuses",
        lambda client, ids: {
            "vid1": {
                "id": "vid1",
                "status": {
                    "uploadStatus": "rejected",
                    "rejectionReason": "inappropriate",
                },
            }
        },
    )
    marked: list[tuple[str, str]] = []
    paused: list[int] = []
    monkeypatch.setattr(
        maintenance.db,
        "mark_youtube_rejected",
        lambda clip_id, reason: marked.append((clip_id, reason)),
    )
    monkeypatch.setattr(
        maintenance.db,
        "pause_automation",
        lambda hours: paused.append(hours),
    )

    assert maintenance.check_upload_statuses(
        object(), pause_hours=12
    ) == ["abc"]
    assert marked == [("abc", "youtube:inappropriate")]
    assert paused == [12]


def test_check_upload_statuses_ignores_processed_videos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Processed videos do not pause or change any clip."""
    monkeypatch.setattr(
        maintenance.db,
        "get_recent_uploads",
        lambda since, limit=50: [{"id": "abc", "youtube_video_id": "vid1"}],
    )
    monkeypatch.setattr(
        "clipmachine.youtube.get_video_statuses",
        lambda client, ids: {"vid1": {"status": {"uploadStatus": "processed"}}},
    )
    monkeypatch.setattr(
        maintenance.db,
        "mark_youtube_rejected",
        lambda *args: pytest.fail("processed video must not be rejected"),
    )
    monkeypatch.setattr(
        maintenance.db,
        "pause_automation",
        lambda *args: pytest.fail("processed video must not pause"),
    )

    assert maintenance.check_upload_statuses(object()) == []
