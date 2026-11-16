"""Expiry and stale-row maintenance shared by upload and render runs."""

from __future__ import annotations

import logging
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
