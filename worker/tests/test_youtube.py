"""Tests for the processing wait and custom thumbnail helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clipmachine import youtube


class FakeRequest:
    """A googleapiclient request stand-in with a fixed response."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def execute(self) -> dict[str, Any]:
        """Return the canned response."""
        return self.response


class FakeVideos:
    """Return queued responses from videos.list."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls = 0

    def list(self, **kwargs: Any) -> FakeRequest:
        """Return the next canned response."""
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return FakeRequest(self.responses[index])


class FakeThumbnails:
    """Record thumbnail set requests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def set(self, **kwargs: Any) -> FakeRequest:
        """Record the call and return an empty response."""
        self.calls.append(kwargs)
        return FakeRequest({})


class FakeClient:
    """Minimal YouTube client for the helper tests."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._videos = FakeVideos(responses)
        self._thumbnails = FakeThumbnails()

    def videos(self) -> FakeVideos:
        """Return the fake videos resource."""
        return self._videos

    def thumbnails(self) -> FakeThumbnails:
        """Return the fake thumbnails resource."""
        return self._thumbnails


def test_wait_for_processing_waits_until_succeeded() -> None:
    """Polling stops once YouTube reports processing succeeded."""
    client = FakeClient(
        [
            {"items": [{"processingDetails": {"processingStatus": "processing"}}]},
            {"items": [{"processingDetails": {"processingStatus": "succeeded"}}]},
        ]
    )

    assert youtube.wait_for_processing(client, "vid", timeout=1, interval=0)
    assert client.videos().calls == 2


def test_wait_for_processing_accepts_processed_upload() -> None:
    """A processed upload status is good enough for a Short."""
    client = FakeClient([{"items": [{"status": {"uploadStatus": "processed"}}]}])

    assert youtube.wait_for_processing(client, "vid", timeout=1, interval=0)


def test_wait_for_processing_gives_up_on_failure() -> None:
    """A failed processing status returns False."""
    client = FakeClient(
        [{"items": [{"processingDetails": {"processingStatus": "failed"}}]}]
    )

    assert not youtube.wait_for_processing(client, "vid", timeout=1, interval=0)


def test_set_thumbnail_calls_thumbnails_set(tmp_path: Path) -> None:
    """set_thumbnail posts the image for the video id."""
    image = tmp_path / "thumb.jpg"
    image.write_bytes(b"fake-jpeg")
    client = FakeClient([])

    youtube.set_thumbnail(client, "vid", image)

    assert client.thumbnails().calls[0]["videoId"] == "vid"
