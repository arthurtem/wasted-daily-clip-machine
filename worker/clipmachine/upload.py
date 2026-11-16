"""Upload approved clips to YouTube in API mode."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from googleapiclient.errors import HttpError

from clipmachine import blob, db, youtube
from clipmachine.config import load_config
from clipmachine.download import clip_dir
from clipmachine.upload_policy import (
    inside_window,
    policy_from_settings,
)

logger = logging.getLogger(__name__)


def _title(clip: dict[str, Any]) -> str:
    """Return the best available YouTube title for a clip."""
    value = clip.get("yt_title") or clip.get("clip_title")
    return str(value) if value else "Wasted Daily Short"


def _tags(clip: dict[str, Any]) -> list[str]:
    """Return a clean list of YouTube tags."""
    value = clip.get("yt_tags")
    return [str(tag) for tag in value] if isinstance(value, list) else []


def _run_upload() -> None:
    """Upload approved clips while UPLOAD_MODE=api, stopping on quota errors."""
    mode = os.environ.get("UPLOAD_MODE", "manual").strip().lower()
    if mode != "api":
        logger.info("manual mode, nothing to do")
        return

    config = load_config()
    settings = config.settings
    stale_hours = getattr(settings, "stale_after_hours", None)
    if stale_hours:
        from clipmachine.maintenance import expire_stale

        expire_stale(int(stale_hours))

    policy = policy_from_settings(settings)
    now = datetime.now(timezone.utc)
    if not inside_window(now, policy):
        logger.info(
            "outside upload window %s-%s %s; nothing to do",
            policy.window_start,
            policy.window_end,
            policy.timezone_name,
        )
        return
    since = now - timedelta(hours=24)
    uploaded_last_24h = db.count_uploads_since(since)
    if uploaded_last_24h >= policy.max_uploads_per_day:
        logger.info(
            "daily upload cap reached (%d/%d)",
            uploaded_last_24h,
            policy.max_uploads_per_day,
        )
        return
    latest = db.latest_upload_at()
    if latest is not None and now - latest < timedelta(
        minutes=policy.min_minutes_between_uploads
    ):
        logger.info(
            "upload gap not met; last upload was %.1f minutes ago",
            (now - latest).total_seconds() / 60,
        )
        return

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

    reddit_priority_hours = int(
        getattr(settings, "reddit_priority_hours", 12)
    )
    requested = max(1, int(getattr(settings, "uploads_per_run", 1)))
    remaining = max(0, policy.max_uploads_per_day - uploaded_last_24h)
    limit = max(1, min(requested, remaining))
    clips = db.get_approved_for_upload(limit, reddit_priority_hours)
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
            if youtube.is_upload_limit_error(exc):
                logger.error("channel daily limit reached")
                return
            if youtube.is_stop_error(exc):
                logger.error(
                    "YouTube API quota reached; retrying next scheduled run"
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

        db.mark_uploaded(clip_id, video_id)
        for url in (clip.get("blob_url"), clip.get("thumb_url")):
            if not url:
                continue
            try:
                blob.delete_url(str(url))
            except Exception:
                logger.warning("clip %s could not delete blob %s", clip_id, url)
        logger.info("clip %s upload complete video_id=%s", clip_id, video_id)



def run_upload() -> None:
    """Run the uploader, serializing uploads in GitHub Actions."""
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        with db.upload_lock() as acquired:
            if not acquired:
                logger.info("another upload is already running; skipping")
                return
            _run_upload()
        return
    _run_upload()
