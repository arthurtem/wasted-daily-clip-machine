"""Tests for the Vercel Blob helper wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from clipmachine import blob


def completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a completed-process result for monkeypatching."""
    return subprocess.CompletedProcess(
        args=["node"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_put_file_returns_public_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """put_file invokes the helper with the local path and pathname."""
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        """Record the helper invocation and return a URL."""
        calls.append(command)
        return completed(0, "https://blob.example/shorts/ClipAbc.mp4\n")

    monkeypatch.setattr(blob.subprocess, "run", fake_run)

    url = blob.put_file(video, "shorts/ClipAbc.mp4")

    assert url == "https://blob.example/shorts/ClipAbc.mp4"
    assert calls[0][1:] == [str(blob.BLOB_HELPER), "put", str(video), "shorts/ClipAbc.mp4"]


def test_delete_url_calls_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """delete_url passes the URL to the delete command."""
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        """Record the helper invocation."""
        calls.append(command)
        return completed(0, "deleted\n")

    monkeypatch.setattr(blob.subprocess, "run", fake_run)

    blob.delete_url("https://blob.example/shorts/ClipAbc.mp4")

    assert calls[0][2:] == ["delete", "https://blob.example/shorts/ClipAbc.mp4"]


def test_helper_failure_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-zero helper exit becomes a BlobError."""
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        blob.subprocess,
        "run",
        lambda command, **kwargs: completed(1, "", "token missing"),
    )

    with pytest.raises(blob.BlobError, match="token missing"):
        blob.put_file(video, "shorts/ClipAbc.mp4")


def test_missing_local_file_raises(tmp_path: Path) -> None:
    """Missing local files are rejected before calling Node."""
    with pytest.raises(blob.BlobError, match="missing file"):
        blob.put_file(tmp_path / "nope.mp4", "shorts/nope.mp4")


def test_invalid_url_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A helper response that is not an https URL is rejected."""
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        blob.subprocess,
        "run",
        lambda command, **kwargs: completed(0, "not-a-url\n"),
    )

    with pytest.raises(blob.BlobError, match="invalid URL"):
        blob.put_file(video, "shorts/ClipAbc.mp4")
