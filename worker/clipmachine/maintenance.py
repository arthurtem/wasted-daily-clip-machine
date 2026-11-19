"""Expiry and stale-row maintenance shared by upload and render runs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from clipmachine import blob, db

logger = logging.getLogger(__name__)


def _delete_clip_blobs(clip: dict[str, Any]) -> bool:
    """Delete a clip's video and thumbnail blobs; return whether all deletes worked."""
    ok = True
    for url in (clip.get("blob_url"), clip.get("thumb_url")):
        if not url:
            continue
        try:
            blob.delete_url(str(url))
        except Exception as exc:
            ok = False
            logger.warning(
                "could not delete stale blob for clip %s: %s",
                clip.get("id"),
                exc,
            )
    return ok


def expire_stale(stale_after_hours: int) -> int:
    """Reject stale approved/rendered clips and remove their Blob files."""
    expired = 0
    for clip in db.get_stale_clips(stale_after_hours):
        deleted = _delete_clip_blobs(clip)
        db.mark_stale(str(clip["id"]), clear_blobs=deleted)
        expired += 1
        logger.info(
            "expired stale clip %s (blobs_deleted=%s)", clip["id"], deleted
        )

    for clip in db.get_stale_rejected_with_blobs():
        if _delete_clip_blobs(clip):
            db.clear_blob_urls(str(clip["id"]))
            logger.info("completed stale blob cleanup for clip %s", clip["id"])
    return expired


def recover_abandoned_renders(minutes: int = 30) -> int:
    """Mark abandoned downloaded rows as timed out so retry is possible."""
    return db.recover_stale_downloads(minutes)


def check_upload_statuses(
    client: Any, *, hours: int = 168, pause_hours: int = 24
) -> list[str]:
    """Detect videos YouTube removed and pause automation after a rejection."""
    from clipmachine import youtube

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    uploads = db.get_recent_uploads(since, limit=1000)
    by_video = {
        str(clip["youtube_video_id"]): clip
        for clip in uploads
        if clip.get("youtube_video_id")
    }
    if not by_video:
        return []

    try:
        statuses = youtube.get_video_statuses(client, list(by_video))
    except Exception as exc:
        logger.warning("could not read YouTube upload statuses: %s", exc)
        return []

    rejected: list[str] = []
    for video_id, item in statuses.items():
        status = item.get("status") or {}
        if str(status.get("uploadStatus") or "").lower() != "rejected":
            continue
        clip = by_video.get(video_id)
        if clip is None:
            continue
        reason = str(status.get("rejectionReason") or "rejected")
        db.mark_youtube_rejected(str(clip["id"]), f"youtube:{reason}")
        rejected.append(str(clip["id"]))

    if statuses:
        for video_id, clip in by_video.items():
            if video_id in statuses:
                continue
            db.mark_youtube_rejected(str(clip["id"]), "youtube:removed")
            rejected.append(str(clip["id"]))
            logger.error(
                "clip %s is no longer available on YouTube", clip["id"]
            )

    logger.info(
        "checked %d recent upload(s): %d removed or rejected",
        len(by_video),
        len(rejected),
    )
    if rejected:
        db.pause_automation(pause_hours)
        logger.error(
            "paused automation for %d hour(s) after %d YouTube rejection(s)",
            pause_hours,
            len(rejected),
        )
    return rejected
