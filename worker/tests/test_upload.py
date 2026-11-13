"""Tests for the API-mode upload runner."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from clipmachine import upload


def config() -> Any:
    """Return the config shape used by run_upload."""
    return SimpleNamespace(settings=SimpleNamespace(uploads_per_run=2))


CLIP = {
    "id": "ClipAbc",
    "blob_url": "https://blob.example/video.mp4",
    "thumb_url": "https://blob.example/thumb.jpg",
    "yt_title": "Title",
    "yt_description": "Description",
    "yt_tags": ["gta"],
    "yt_privacy": "unlisted",
}


def test_manual_mode_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Manual mode exits before touching the database."""
    monkeypatch.setenv("UPLOAD_MODE", "manual")
    monkeypatch.setattr(
        upload, "load_config", lambda: pytest.fail("should not load config")
    )

    upload.run_upload()


def test_no_connection_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """No connection row exits without changing clips."""
    monkeypatch.setenv("UPLOAD_MODE", "api")
    monkeypatch.setattr(upload, "load_config", config)
    monkeypatch.setattr(upload.db, "get_youtube_connection", lambda: None)
    monkeypatch.setattr(
        upload.db, "get_clips", lambda *args: pytest.fail("should not fetch")
    )
    monkeypatch.setattr(
        upload.db, "set_status", lambda *args, **kwargs: pytest.fail("no status")
    )

    upload.run_upload()


def test_invalid_grant_deletes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A revoked refresh token deletes the row and leaves clips approved."""
    monkeypatch.setenv("UPLOAD_MODE", "api")
    monkeypatch.setattr(upload, "load_config", config)
    monkeypatch.setattr(
        upload.db,
        "get_youtube_connection",
        lambda: {"refresh_token_enc": "encrypted", "scopes": ""},
    )
    monkeypatch.setattr(
        upload.youtube,
        "get_client",
        lambda connection: (_ for _ in ()).throw(
            upload.youtube.InvalidGrantError("invalid_grant")
        ),
    )
    deleted: list[bool] = []
    monkeypatch.setattr(
        upload.db,
        "delete_youtube_connection",
        lambda: deleted.append(True),
    )
    monkeypatch.setattr(
        upload.db, "get_clips", lambda *args: pytest.fail("should not fetch")
    )
    monkeypatch.setattr(
        upload.db, "set_status", lambda *args, **kwargs: pytest.fail("no status")
    )

    upload.run_upload()

    assert deleted == [True]


def test_success_marks_uploaded_and_deletes_blobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful upload stores the video id and removes both blobs."""
    monkeypatch.setenv("UPLOAD_MODE", "api")
    monkeypatch.setattr(upload, "load_config", config)
    monkeypatch.setattr(
        upload.db,
        "get_youtube_connection",
        lambda: {"refresh_token_enc": "encrypted", "scopes": ""},
    )
    monkeypatch.setattr(
        upload.youtube, "get_client", lambda connection: object()
    )
    monkeypatch.setattr(upload.db, "get_clips", lambda status, limit: [CLIP])
    monkeypatch.setattr(
        upload.blob, "download_file", lambda url, target: target
    )
    uploaded: list[dict[str, Any]] = []

    def fake_upload_short(*args: Any) -> str:
        """Record the upload arguments and return a fake id."""
        uploaded.append(
            {
                "path": args[1],
                "privacy": args[5],
            }
        )
        return "video-id"

    monkeypatch.setattr(upload.youtube, "upload_short", fake_upload_short)
    statuses: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        upload.db,
        "set_status",
        lambda clip_id, status, error=None, **fields: statuses.append(
            (clip_id, status, error, fields)
        ),
    )
    deleted: list[str] = []
    monkeypatch.setattr(
        upload.blob, "delete_url", lambda url: deleted.append(url)
    )

    upload.run_upload()

    assert uploaded[0]["privacy"] == "unlisted"
    assert ("ClipAbc", "uploaded", None, {"youtube_video_id": "video-id"}) in statuses
    assert deleted == [CLIP["blob_url"], CLIP["thumb_url"]]


def test_quota_error_stops_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """quotaExceeded stops without marking the clip failed."""
    monkeypatch.setenv("UPLOAD_MODE", "api")
    monkeypatch.setattr(upload, "load_config", config)
    monkeypatch.setattr(
        upload.db,
        "get_youtube_connection",
        lambda: {"refresh_token_enc": "encrypted", "scopes": ""},
    )
    monkeypatch.setattr(
        upload.youtube, "get_client", lambda connection: object()
    )
    second = dict(CLIP, id="ClipSecond", blob_url="https://blob.example/2.mp4")
    monkeypatch.setattr(
        upload.db, "get_clips", lambda status, limit: [CLIP, second]
    )
    downloads: list[str] = []
    monkeypatch.setattr(
        upload.blob,
        "download_file",
        lambda url, target: downloads.append(url) or target,
    )
    error = HttpError(
        Response({"status": 403}),
        b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}',
        uri="",
    )

    def fail_upload(*args: Any) -> str:
        """Raise the quota error."""
        raise error

    monkeypatch.setattr(upload.youtube, "upload_short", fail_upload)
    monkeypatch.setattr(
        upload.db, "set_status", lambda *args, **kwargs: pytest.fail("no status")
    )

    upload.run_upload()

    assert downloads == [CLIP["blob_url"]]
