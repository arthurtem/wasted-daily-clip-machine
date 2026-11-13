"""Download Twitch clips to the local work directory with yt-dlp."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yt_dlp

from clipmachine import db

logger = logging.getLogger(__name__)

WORK_DIR_ENV = "CLIPMACHINE_WORK_DIR"
DEFAULT_WORK_ROOT = Path(__file__).resolve().parents[2] / "work"
MAX_HEIGHT = 1080


class DownloadError(RuntimeError):
    """Raised when a clip cannot be downloaded."""


def work_root(explicit: Path | None = None) -> Path:
    """Resolve the work directory from an argument, env var, or repo default."""
    if explicit is not None:
        return Path(explicit)
    env_value = os.environ.get(WORK_DIR_ENV, "").strip()
    if env_value:
        return Path(env_value)
    return DEFAULT_WORK_ROOT


def clip_dir(clip_id: str, root: Path | None = None) -> Path:
    """Return and create the work directory for one clip."""
    directory = work_root(root) / clip_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _yt_dlp_options(target: Path) -> dict[str, Any]:
    """Build yt-dlp options for a best mp4 download capped at 1080p."""
    return {
        "format": (
            f"best[ext=mp4][height<={MAX_HEIGHT}]/"
            f"best[height<={MAX_HEIGHT}]/best"
        ),
        "outtmpl": str(target.parent / "source.%(ext)s"),
        "merge_output_format": "mp4",
        "postprocessors": [
            {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 2,
        "socket_timeout": 30,
    }


def download_video(
    clip_id: str, url: str, root: Path | None = None
) -> Path:
    """Download a clip URL to work/<id>/source.mp4 and return the path."""
    target = clip_dir(clip_id, root) / "source.mp4"
    logger.info("clip %s download start url=%s", clip_id, url)
    with yt_dlp.YoutubeDL(_yt_dlp_options(target)) as ydl:
        ydl.download([url])
    if not target.exists():
        raise DownloadError(f"yt-dlp did not produce {target.name}")
    return target


def download_clip(
    clip: Mapping[str, Any], root: Path | None = None
) -> Path | None:
    """Download one clip to work/<id>/source.mp4 and set its database status."""
    clip_id = str(clip.get("id") or "")
    url = clip.get("clip_url")
    if not clip_id:
        logger.error("download skipped: clip has no id")
        return None
    if not isinstance(url, str) or not url:
        db.set_status(clip_id, "failed", error="clip_url is missing")
        logger.error("clip %s download failed: clip_url is missing", clip_id)
        return None

    try:
        target = download_video(clip_id, url, root)
    except Exception as exc:
        logger.error("clip %s download failed: %s", clip_id, exc)
        db.set_status(clip_id, "failed", error=str(exc))
        return None

    db.set_status(clip_id, "downloaded")
    logger.info("clip %s downloaded to %s", clip_id, target)
    return target
