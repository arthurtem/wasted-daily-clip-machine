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
