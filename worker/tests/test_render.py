"""Tests for the ffmpeg filter graph builder and a real render smoke test."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from clipmachine.facecam import Layout
from clipmachine.render import (
    RenderError,
    build_filtergraph,
    probe_video,
    render_vertical,
)


def test_cam_top_graph() -> None:
    """cam_top stacks a 640px cam over 1280px of gameplay."""
    layout = Layout("cam_top", (100, 100, 600, 400), 0.9)

    graph = build_filtergraph(layout, 1920, 1080)

    assert "crop=600:400:100:100" in graph
    assert "scale=1080:640:force_original_aspect_ratio=increase" in graph
    assert "crop=1080:640" in graph
    assert "crop=910:1080:505:0" in graph
    assert "scale=1080:1280:force_original_aspect_ratio=increase" in graph
    assert "crop=1080:1280" in graph
    assert "vstack=inputs=2" in graph


def test_no_cam_graph() -> None:
    """no_cam uses a blurred cover background and a centered foreground."""
    graph = build_filtergraph(Layout("no_cam", None, 1.0), 1920, 1080)

    assert "scale=1080:1920:force_original_aspect_ratio=increase" in graph
    assert "crop=1080:1920" in graph
    assert "boxblur=20" in graph
    assert "eq=brightness=-0.08" in graph
    assert "scale=1080:-2" in graph
    assert "overlay=(W-w)/2:(H-h)/2" in graph


def test_full_face_graph() -> None:
    """full_face center-crops to 9:16 and scales to 1080x1920."""
    graph = build_filtergraph(Layout("full_face", None, 1.0), 1920, 1080)

    assert "crop=606:1080:657:0" in graph
    assert "scale=1080:1920" in graph


def test_unknown_layout_raises() -> None:
    """An unsupported layout kind is a render error."""
    with pytest.raises(RenderError, match="unknown layout kind"):
        build_filtergraph(Layout("side_by_side", None, 1.0), 1920, 1080)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)
def test_render_no_cam_outputs_1080x1920(tmp_path: Path) -> None:
    """A generated 1920x1080 test video renders to a 1080x1920 Short."""
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=1920x1080:rate=30:duration=5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "vertical.mp4"

    render_vertical(source, Layout("no_cam", None, 1.0), output)

    assert probe_video(output) == (1080, 1920)


def _has_filter(name: str) -> bool:
    """Return whether the configured ffmpeg has a named filter."""
    from clipmachine.render import ffmpeg_bin

    try:
        result = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-h", f"filter={name}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def test_final_graph_includes_captions(tmp_path: Path) -> None:
    """The final graph chains the layout and ASS captions."""
    from clipmachine.render import build_final_filtergraph

    graph = build_final_filtergraph(
        Layout("cam_top", (0, 0, 400, 300), 1.0),
        1920,
        1080,
        tmp_path / "captions.ass",
    )

    assert "ass=filename=" in graph
    assert "captions.ass" in graph
    assert "drawtext" not in graph
    assert "[vout]" in graph


def test_final_graph_without_captions_uses_null() -> None:
    """No transcript still produces a valid graph without drawtext."""
    from clipmachine.render import build_final_filtergraph

    graph = build_final_filtergraph(
        Layout("no_cam", None, 1.0), 1920, 1080, None
    )

    assert "ass=filename=" not in graph
    assert "drawtext" not in graph
    assert graph.endswith("null[vout]")


@pytest.mark.skipif(
    not _has_filter("ass"),
    reason="ffmpeg lacks the ass filter",
)
def test_render_final_with_captions(tmp_path: Path) -> None:
    """A generated clip renders with ASS captions and a thumbnail."""
    from clipmachine.captions import build_ass
    from clipmachine.render import render_final

    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=1920x1080:rate=30:duration=3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    layout = Layout("no_cam", None, 1.0)
    words = [
        {"word": "hello", "start": 0.2, "end": 0.6},
        {"word": "world", "start": 0.7, "end": 1.1},
    ]
    ass_path = build_ass(words, layout, tmp_path / "captions.ass")
    final = tmp_path / "final.mp4"
    thumb = tmp_path / "thumb.jpg"

    render_final(source, layout, final, thumb, ass_path)

    assert probe_video(final) == (1080, 1920)
    assert thumb.exists()
