"""Upload approved clips to YouTube in API mode."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from googleapiclient.errors import HttpError

from clipmachine import blob, db, youtube
from clipmachine.config import load_config
from clipmachine.download import clip_dir

logger = logging.getLogger(__name__)


def _title(clip: dict[str, Any]) -> str:
    """Return the best available YouTube title for a clip."""
    value = clip.get("yt_title") or clip.get("clip_title")
    return str(value) if value else "Wasted Daily Short"


def _tags(clip: dict[str, Any]) -> list[str]:
    """Return a clean list of YouTube tags."""
    value = clip.get("yt_tags")
    return [str(tag) for tag in value] if isinstance(value, list) else []


def run_upload() -> None:
    """Upload approved clips while UPLOAD_MODE=api, stopping on quota errors."""
    mode = os.environ.get("UPLOAD_MODE", "manual").strip().lower()
    if mode != "api":
        logger.info("manual mode, nothing to do")
        return

    config = load_config()
    connection = db.get_youtube_connection()
    if connection is None:
        logger.info("YouTube not connected")
        return

    try:
        client = youtube.get_client(connection)
    except youtube.InvalidGrantError:
        logger.error("YouTube refresh token is invalid; deleting connection")
        db.delete_youtube_connection()
        return
    except youtube.YouTubeError as exc:
        logger.error("YouTube client unavailable: %s", exc)
        return

    clips = db.get_clips("approved", config.settings.uploads_per_run)
    if not clips:
        logger.info("no approved clips to upload")
        return

    for clip in clips:
        clip_id = str(clip.get("id") or "")
        blob_url = clip.get("blob_url")
        if not blob_url:
            db.set_status(
                clip_id, "failed", error="clip has no blob_url"
            )
            logger.error("clip %s has no blob_url", clip_id)
            continue

        target = clip_dir(clip_id) / "youtube.mp4"
        try:
            blob.download_file(str(blob_url), target)
            video_id = youtube.upload_short(
                client,
                target,
                _title(clip),
                str(clip.get("yt_description") or ""),
                _tags(clip),
                str(clip.get("yt_privacy") or ""),
            )
        except HttpError as exc:
            if youtube.is_stop_error(exc):
                logger.error(
                    "clip %s upload stopped by quota/upload limit: %s",
                    clip_id,
                    exc,
                )
                return
            logger.exception("clip %s upload failed", clip_id)
            db.set_status(clip_id, "failed", error=str(exc))
            continue
        except Exception as exc:
            logger.exception("clip %s upload failed", clip_id)
            db.set_status(clip_id, "failed", error=str(exc))
            continue
        finally:
            try:
                target.unlink(missing_ok=True)
                target.parent.rmdir()
            except OSError:
                pass

        db.set_status(clip_id, "uploaded", youtube_video_id=video_id)
        for url in (clip.get("blob_url"), clip.get("thumb_url")):
            if not url:
                continue
            try:
                blob.delete_url(str(url))
            except Exception:
                logger.warning("clip %s could not delete blob %s", clip_id, url)
        logger.info("clip %s upload complete video_id=%s", clip_id, video_id)
