"""Tests for clip downloading with a fake yt-dlp."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clipmachine import download
from clipmachine.download import download_clip

CLIP = {"id": "ClipAbc", "clip_url": "https://clips.twitch.tv/ClipAbc"}


class FakeYDL:
    """Fake YoutubeDL that writes the expected output file."""

    instances: list[FakeYDL] = []

    def __init__(self, options: dict[str, Any]) -> None:
        """Store the yt-dlp options and register the instance."""
        self.options = options
        self.urls: list[str] = []
        FakeYDL.instances.append(self)

    def __enter__(self) -> FakeYDL:
        """Enter the downloader context."""
        return self

    def __exit__(self, *exc_info: object) -> bool:
        """Leave the downloader context without suppressing errors."""
        return False

    def download(self, urls: list[str]) -> None:
        """Record the urls and create the output file."""
        self.urls.extend(urls)
        template = Path(self.options["outtmpl"])
        target = Path(str(template).replace("%(ext)s", "mp4"))
        target.write_bytes(b"fake mp4")


class FailingYDL(FakeYDL):
    """Fake YoutubeDL that always fails."""

    def download(self, urls: list[str]) -> None:
        """Raise a download failure."""
        raise RuntimeError("boom")


@pytest.fixture
def statuses(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Capture set_status calls made by the downloader."""
    calls: list[tuple[Any, ...]] = []

    def fake_set_status(
        clip_id: str, status: str, error: str | None = None, **fields: Any
    ) -> bool:
        """Record a status update."""
        calls.append((clip_id, status, error))
        return True

    monkeypatch.setattr(download.db, "set_status", fake_set_status)
    FakeYDL.instances.clear()
    return calls


def test_download_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    statuses: list[tuple[Any, ...]],
) -> None:
    """A successful download writes source.mp4 and marks the clip downloaded."""
    monkeypatch.setattr(download.yt_dlp, "YoutubeDL", FakeYDL)

    path = download_clip(CLIP, tmp_path)

    assert path == tmp_path / "ClipAbc" / "source.mp4"
    assert path is not None and path.exists()
    assert statuses == [("ClipAbc", "downloaded", None)]
    options = FakeYDL.instances[0].options
    assert "ext=mp4" in options["format"]
    assert "height<=1080" in options["format"]
    assert options["outtmpl"].endswith("source.%(ext)s")
    assert options["postprocessors"][0]["preferedformat"] == "mp4"
    assert FakeYDL.instances[0].urls == [CLIP["clip_url"]]


def test_download_failure_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    statuses: list[tuple[Any, ...]],
) -> None:
    """A yt-dlp error marks the clip failed and returns None."""
    monkeypatch.setattr(download.yt_dlp, "YoutubeDL", FailingYDL)

    path = download_clip(CLIP, tmp_path)

    assert path is None
    assert statuses == [("ClipAbc", "failed", "boom")]


def test_download_without_url_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    statuses: list[tuple[Any, ...]],
) -> None:
    """A clip without a URL is marked failed without calling yt-dlp."""
    monkeypatch.setattr(download.yt_dlp, "YoutubeDL", FakeYDL)

    path = download_clip({"id": "ClipAbc"}, tmp_path)

    assert path is None
    assert statuses == [("ClipAbc", "failed", "clip_url is missing")]
    assert FakeYDL.instances == []
