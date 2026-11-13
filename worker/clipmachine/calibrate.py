"""Build a calibration frame for choosing a streamer's facecam box."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cv2

from clipmachine.config import Streamer, load_config
from clipmachine.download import clip_dir, download_video
from clipmachine.facecam import (
    CORNER_OVERRIDES,
    Box,
    _sample_frames,
    fractional_cam_box,
    preset_cam_box,
)
from clipmachine.twitch import TwitchClient

logger = logging.getLogger(__name__)

GRID_STEP = 100


class CalibrateError(RuntimeError):
    """Raised when a calibration frame cannot be produced."""


def find_streamer(
    login: str, config_directory: Path | None = None
) -> Streamer:
    """Return the configured streamer for a Twitch login."""
    config = load_config(config_directory)
    for streamer in config.streamers:
        if streamer.twitch_login.lower() == login.lower():
            return streamer
    raise CalibrateError(f"unknown streamer {login!r} in streamers.yaml")


def latest_clip_url(
    streamer: Streamer, config_directory: Path | None = None
) -> tuple[str, str]:
    """Return the id and URL of the streamer's most viewed recent clip."""
    config = load_config(config_directory)
    client = TwitchClient()
    logins = client.get_user_ids([streamer.twitch_login])
    broadcaster_id = logins.get(streamer.twitch_login.lower())
    if broadcaster_id is None:
        raise CalibrateError(
            f"Twitch returned no user for {streamer.twitch_login!r}"
        )
    ended_at = datetime.now(timezone.utc)
    started_at = ended_at - timedelta(hours=config.settings.lookback_hours)
    clips = [
        clip
        for clip in client.get_clips(broadcaster_id, started_at, ended_at)
        if clip.get("id") and clip.get("url")
    ]
    if not clips:
        raise CalibrateError(
            f"no clips for {streamer.twitch_login!r} in the last "
            f"{config.settings.lookback_hours}h; pass --clip-id instead"
        )
    clips.sort(key=lambda clip: int(clip.get("view_count") or 0), reverse=True)
    return str(clips[0]["id"]), str(clips[0]["url"])


def write_calibration_image(
    source: Path, out_path: Path, streamer: Streamer
) -> Path:
    """Write a gridded middle frame with the current cam box highlighted."""
    frames, frame_w, frame_h = _sample_frames(source)
    image = frames[len(frames) // 2].copy()

    for x in range(0, frame_w, GRID_STEP):
        cv2.line(image, (x, 0), (x, frame_h), (0, 255, 255), 1)
        cv2.putText(
            image,
            str(x),
            (x + 3, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
        )
    for y in range(0, frame_h, GRID_STEP):
        cv2.line(image, (0, y), (frame_w, y), (0, 255, 255), 1)
        cv2.putText(
            image,
            str(y),
            (3, y + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
        )

    current_box: Box | None = None
    if streamer.facecam_box is not None:
        current_box = fractional_cam_box(
            streamer.facecam_box, frame_w, frame_h
        )
    elif streamer.facecam_override in CORNER_OVERRIDES:
        current_box = preset_cam_box(
            streamer.facecam_override, frame_w, frame_h
        )
    if current_box is not None:
        box_x, box_y, box_w, box_h = current_box
        cv2.rectangle(
            image,
            (box_x, box_y),
            (box_x + box_w, box_y + box_h),
            (0, 255, 0),
            3,
        )

    cv2.putText(
        image,
        f"{frame_w}x{frame_h}",
        (12, frame_h - 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), image)
    return out_path


def run_calibrate(
    login: str,
    clip_id: str | None = None,
    config_directory: Path | None = None,
    work_root: Path | None = None,
) -> tuple[Path, Streamer]:
    """Write a calibration frame for a streamer and return it."""
    streamer = find_streamer(login, config_directory)
    if clip_id:
        source = clip_dir(clip_id, work_root) / "source.mp4"
        if not source.exists():
            raise CalibrateError(f"missing source video: {source}")
    else:
        clip_id, clip_url = latest_clip_url(streamer, config_directory)
        source = download_video(clip_id, clip_url, work_root)

    image_path = write_calibration_image(
        source, source.parent / "calibrate.jpg", streamer
    )
    logger.info(
        "clip %s calibration image=%s", source.parent.name, image_path
    )
    return image_path, streamer
