"""Tests for the facecam calibration frame helper."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from clipmachine.calibrate import CalibrateError, run_calibrate


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is required"
)
def test_calibrate_writes_grid_image(
    tmp_path: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An already downloaded clip produces a calibration image."""
    clip = "ClipAbc"
    source = tmp_path / clip / "source.mp4"
    source.parent.mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=10:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
        capture_output=True,
    )

    image, streamer = run_calibrate(
        "kaicenat", clip, config_dir, tmp_path
    )

    assert streamer.twitch_login == "kaicenat"
    assert image == source.parent / "calibrate.jpg"
    assert image.exists()


def test_calibrate_rejects_unknown_streamer(
    tmp_path: Path, config_dir: Path
) -> None:
    """An unknown login raises a clear error."""
    with pytest.raises(CalibrateError, match="unknown streamer"):
        run_calibrate("nobody", "ClipAbc", config_dir, tmp_path)
