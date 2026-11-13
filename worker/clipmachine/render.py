"""Render downloaded clips into 1080x1920 Shorts with ffmpeg."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from clipmachine.facecam import Layout

logger = logging.getLogger(__name__)

OUT_WIDTH = 1080
OUT_HEIGHT = 1920
CAM_HEIGHT = 640
GAME_HEIGHT = 1280
OUT_FPS = 30
FFMPEG_ENV = "FFMPEG_BIN"
FFPROBE_ENV = "FFPROBE_BIN"


def ffmpeg_bin() -> str:
    """Return the ffmpeg binary path from the environment or PATH."""
    return os.environ.get(FFMPEG_ENV, "").strip() or "ffmpeg"


def ffprobe_bin() -> str:
    """Return the ffprobe binary path from the environment or PATH."""
    return os.environ.get(FFPROBE_ENV, "").strip() or "ffprobe"


class RenderError(RuntimeError):
    """Raised when ffmpeg cannot render a clip."""


def _even(value: float | int) -> int:
    """Round down to the nearest positive even integer."""
    number = int(value)
    return max(2, number - number % 2)


def _clamp_box(box: tuple[int, int, int, int], frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
    """Clamp a crop box inside the frame using even offsets and sizes."""
    x, y, width, height = box
    x = max(0, min(int(x), frame_w - 2))
    y = max(0, min(int(y), frame_h - 2))
    width = _even(min(int(width), frame_w - x))
    height = _even(min(int(height), frame_h - y))
    x = min(x - x % 2, frame_w - width)
    y = min(y - y % 2, frame_h - height)
    return (x, y, width, height)


def _center_crop(
    src_w: int, src_h: int, aspect: float
) -> tuple[int, int, int, int]:
    """Return an even-sized centered crop matching the target aspect ratio."""
    if src_w / src_h > aspect:
        height = _even(src_h)
        width = _even(min(src_w, height * aspect))
        x = (src_w - width) // 2
        y = 0
    else:
        width = _even(src_w)
        height = _even(min(src_h, width / aspect))
        x = 0
        y = (src_h - height) // 2
    return (x, y, width, height)


def build_filtergraph(layout: Layout, src_w: int, src_h: int) -> str:
    """Build the ffmpeg filter_complex graph for a layout."""
    if src_w <= 0 or src_h <= 0:
        raise RenderError(f"invalid source size {src_w}x{src_h}")

    if layout.kind == "cam_top":
        if layout.cam_box is None:
            raise RenderError("cam_top layout has no cam_box")
        cam_x, cam_y, cam_w, cam_h = _clamp_box(layout.cam_box, src_w, src_h)
        game_x, game_y, game_w, game_h = _center_crop(
            src_w, src_h, OUT_WIDTH / GAME_HEIGHT
        )
        return (
            "[0:v]split=2[camsrc][gamesrc];"
            f"[camsrc]crop={cam_w}:{cam_h}:{cam_x}:{cam_y},"
            f"scale={OUT_WIDTH}:{CAM_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={OUT_WIDTH}:{CAM_HEIGHT},setsar=1[cam];"
            f"[gamesrc]crop={game_w}:{game_h}:{game_x}:{game_y},"
            f"scale={OUT_WIDTH}:{GAME_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={OUT_WIDTH}:{GAME_HEIGHT},setsar=1[game];"
            "[cam][game]vstack=inputs=2[v]"
        )

    if layout.kind == "no_cam":
        return (
            "[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={OUT_WIDTH}:{OUT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={OUT_WIDTH}:{OUT_HEIGHT},boxblur=20,eq=brightness=-0.08[bg];"
            f"[fgsrc]scale={OUT_WIDTH}:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )

    if layout.kind == "full_face":
        crop_x, crop_y, crop_w, crop_h = _center_crop(
            src_w, src_h, OUT_WIDTH / OUT_HEIGHT
        )
        return (
            f"[0:v]crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
            f"scale={OUT_WIDTH}:{OUT_HEIGHT},setsar=1[v]"
        )

    raise RenderError(f"unknown layout kind {layout.kind!r}")


def probe_video(path: Path) -> tuple[int, int]:
    """Return the first video stream's width and height."""
    command = [
        ffprobe_bin(),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(f"ffprobe failed: {result.stderr[-500:]}")
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise RenderError("ffprobe returned invalid JSON") from exc
    streams = payload.get("streams") or []
    if not streams:
        raise RenderError(f"no video stream found in {path}")
    return int(streams[0]["width"]), int(streams[0]["height"])


def render_vertical(source: Path, layout: Layout, out_path: Path) -> None:
    """Render one clip to a 1080x1920 H.264/AAC Short."""
    src_w, src_h = probe_video(source)
    graph = build_filtergraph(layout, src_w, src_h)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-r",
        str(OUT_FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(
            f"ffmpeg failed ({result.returncode}): {result.stderr[-500:]}"
        )
    logger.info(
        "clip %s rendered layout=%s output=%s",
        out_path.parent.name,
        layout.kind,
        out_path,
    )


def _escape_filter_path(path: Path) -> str:
    """Escape a path for use inside an ffmpeg filter option."""
    value = str(path).replace("\\", "\\\\").replace("'", "\\'")
    for character in (":", ",", "[", "]", ";"):
        value = value.replace(character, "\\" + character)
    return value


def build_final_filtergraph(
    layout: Layout,
    src_w: int,
    src_h: int,
    ass_path: Path | None = None,
) -> str:
    """Build the layout graph plus optional ASS captions."""
    graph = build_filtergraph(layout, src_w, src_h)
    current = "v"
    if ass_path is not None:
        escaped = _escape_filter_path(ass_path)
        graph += f";[{current}]ass=filename='{escaped}'[captioned]"
        current = "captioned"
    graph += f";[{current}]null[vout]"
    return graph


def render_final(
    source: Path,
    layout: Layout,
    out_path: Path,
    thumb_path: Path,
    ass_path: Path | None = None,
) -> None:
    """Render the vertical Short with captions, plus a thumbnail."""
    src_w, src_h = probe_video(source)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    graph = build_final_filtergraph(layout, src_w, src_h, ass_path)
    command = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        graph,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        "-r",
        str(OUT_FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(
            f"ffmpeg failed ({result.returncode}): {result.stderr[-500:]}"
        )
    logger.info(
        "clip %s final rendered layout=%s output=%s",
        out_path.parent.name,
        layout.kind,
        out_path,
    )

    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_command = [
        ffmpeg_bin(),
        "-y",
        "-ss",
        "1",
        "-i",
        str(out_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(thumb_path),
    ]
    thumb_result = subprocess.run(thumb_command, capture_output=True, text=True)
    if thumb_result.returncode != 0:
        raise RenderError(
            "thumbnail extraction failed: "
            f"{thumb_result.stderr[-500:]}"
        )
    logger.info("clip %s thumbnail=%s", out_path.parent.name, thumb_path)
