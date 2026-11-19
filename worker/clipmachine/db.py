"""Postgres access for clip rows and schema migrations."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from clipmachine.models import NewClip

logger = logging.getLogger(__name__)

STATUSES = frozenset(
    {"new", "downloaded", "rendered", "approved", "uploaded", "rejected", "failed"}
)
UPDATABLE_FIELDS = frozenset(
    {
        "layout",
        "blob_url",
        "thumb_url",
        "yt_title",
        "yt_description",
        "yt_tags",
        "youtube_video_id",
        "reddit_score",
        "reddit_url",
        "reddit_id",
        "reddit_subreddit",
        "reddit_comments",
        "thumbnail_url",
        "uploaded_at",
        "auto_rendered_at",
        "yt_privacy",
        "moderation_level",
        "moderation_score",
        "moderation_labels",
    }
)
MIGRATIONS_DIR_ENV = "MIGRATIONS_DIR"
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


class DatabaseError(RuntimeError):
    """Raised when the database cannot be configured or reached."""


def database_url(environ: Mapping[str, str] | None = None) -> str:
    """Return DATABASE_URL or raise a clear configuration error."""
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "").strip()
    if not value:
        raise DatabaseError(
            "DATABASE_URL is not set; add a Postgres connection string to your environment"
        )
    return value


def migrations_dir(explicit: Path | None = None) -> Path:
    """Resolve the migrations directory from an argument, env var, or repo default."""
    if explicit is not None:
        return Path(explicit)
    env_value = os.environ.get(MIGRATIONS_DIR_ENV, "").strip()
    if env_value:
        return Path(env_value)
    return DEFAULT_MIGRATIONS_DIR


def connect(row_factory: Any | None = None) -> psycopg.Connection[Any]:
    """Open a Postgres connection using DATABASE_URL."""
    kwargs: dict[str, Any] = {}
    if row_factory is not None:
        kwargs["row_factory"] = row_factory
    return psycopg.connect(database_url(), **kwargs)


def _validate_status(status: str) -> None:
    """Reject statuses outside the supported clip lifecycle."""
    if status not in STATUSES:
        allowed = ", ".join(sorted(STATUSES))
        raise ValueError(f"unknown clip status {status!r}; expected one of {allowed}")


def init_db(migrations_path: Path | None = None) -> None:
    """Apply every .sql migration in sorted order, idempotently."""
    directory = migrations_dir(migrations_path)
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise DatabaseError(f"no migrations found in {directory}")
    with connect() as conn:
        for path in files:
            conn.execute(path.read_text(encoding="utf-8"))
            logger.info("applied migration %s", path.name)


def upsert_new_clip(clip: NewClip) -> bool:
    """Insert a clip unless its Twitch id already exists; return whether it was inserted."""
    query = """
        INSERT INTO clips (
            id, source, streamer_login, streamer_name, clip_title, clip_url,
            view_count, duration_s, clip_created_at, thumbnail_url,
            reddit_score, reddit_url, reddit_id, reddit_subreddit,
            reddit_comments
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """
    params = (
        clip.id,
        clip.source,
        clip.streamer_login,
        clip.streamer_name,
        clip.clip_title,
        clip.clip_url,
        clip.view_count,
        clip.duration_s,
        clip.clip_created_at,
        clip.thumbnail_url,
        clip.reddit_score,
        clip.reddit_url,
        clip.reddit_id,
        clip.reddit_subreddit,
        clip.reddit_comments,
    )
    with connect() as conn:
        inserted = conn.execute(query, params).rowcount == 1
    logger.info("clip %s upsert inserted=%s", clip.id, inserted)
    return inserted


def get_clips(status: str, limit: int = 100) -> list[dict[str, Any]]:
    """Return clips with a given status, newest first."""
    _validate_status(status)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    with connect(row_factory=dict_row) as conn:
        cursor = conn.execute(
            "SELECT * FROM clips WHERE status = %s ORDER BY created_at DESC LIMIT %s",
            (status, limit),
        )
        rows = cursor.fetchall()
    return list(rows)


def set_status(
    clip_id: str, status: str, error: str | None = None, **fields: Any
) -> bool:
    """Update a clip's status, error message, and whitelisted fields."""
    _validate_status(status)
    unknown = set(fields) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"unknown clip fields: {', '.join(sorted(unknown))}")

    assignments = [sql.SQL("status = %s"), sql.SQL("error = %s"), sql.SQL("updated_at = now()")]
    params: list[Any] = [status, error]
    for name in sorted(fields):
        value = fields[name]
        if name == "layout":
            value = Jsonb(value)
        assignments.append(sql.SQL("{} = %s").format(sql.Identifier(name)))
        params.append(value)
    params.append(clip_id)
    query = sql.SQL("UPDATE clips SET {} WHERE id = %s").format(
        sql.SQL(", ").join(assignments)
    )

    with connect() as conn:
        updated = conn.execute(query, params).rowcount == 1
    if updated:
        logger.info("clip %s status -> %s", clip_id, status)
    else:
        logger.warning("clip %s not found while setting status %s", clip_id, status)
    return updated


def get_youtube_connection() -> dict[str, Any] | None:
    """Return the single stored YouTube connection, including the encrypted token."""
    with connect(row_factory=dict_row) as conn:
        cursor = conn.execute(
            """
            SELECT id, channel_id, channel_title, refresh_token_enc, scopes,
                   connected_at
            FROM youtube_connection
            WHERE id = 1
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    return dict(row) if row else None


def delete_youtube_connection() -> None:
    """Delete the stored YouTube connection."""
    with connect() as conn:
        conn.execute("DELETE FROM youtube_connection WHERE id = 1")
    logger.info("deleted stored YouTube connection")



def update_clip_metadata(
    clip_id: str,
    *,
    thumbnail_url: str | None = None,
    reddit_score: int | None = None,
    reddit_url: str | None = None,
    reddit_id: str | None = None,
    reddit_subreddit: str | None = None,
    reddit_comments: int | None = None,
) -> bool:
    """Refresh preview and Reddit metadata on an existing clip."""
    with connect() as conn:
        updated = conn.execute(
            """
            UPDATE clips
            SET thumbnail_url = COALESCE(%s, thumbnail_url),
                reddit_score = COALESCE(%s, reddit_score),
                reddit_url = COALESCE(%s, reddit_url),
                reddit_id = COALESCE(%s, reddit_id),
                reddit_subreddit = COALESCE(%s, reddit_subreddit),
                reddit_comments = COALESCE(%s, reddit_comments),
                updated_at = now()
            WHERE id = %s
            """,
            (
                thumbnail_url,
                reddit_score,
                reddit_url,
                reddit_id,
                reddit_subreddit,
                reddit_comments,
                clip_id,
            ),
        ).rowcount == 1
    return updated


def get_new_clips(limit: int = 100) -> list[dict[str, Any]]:
    """Return imported clips that have not been rendered yet."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    with connect(row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT * FROM clips
            WHERE status = 'new'
            ORDER BY clip_created_at DESC NULLS LAST, view_count DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return list(rows)


def get_new_clips_by_ids(clip_ids: list[str]) -> list[dict[str, Any]]:
    """Return new clips with the given ids in caller order."""
    cleaned = [str(clip_id) for clip_id in clip_ids if str(clip_id)]
    if not cleaned:
        return []
    with connect(row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT * FROM clips
            WHERE status = 'new' AND id = ANY(%s)
            """,
            (cleaned,),
        ).fetchall()
    by_id = {str(row["id"]): dict(row) for row in rows}
    return [by_id[clip_id] for clip_id in cleaned if clip_id in by_id]


def get_approved_for_upload(
    limit: int, reddit_priority_hours: int
) -> list[dict[str, Any]]:
    """Return approved clips in upload priority order."""
    with connect(row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT * FROM clips
            WHERE status = 'approved'
            ORDER BY
                CASE
                    WHEN reddit_score IS NOT NULL
                     AND clip_created_at >= now() - make_interval(hours => %s)
                    THEN 0
                    ELSE 1
                END,
                clip_created_at DESC NULLS LAST,
                created_at DESC
            LIMIT %s
            """,
            (reddit_priority_hours, limit),
        ).fetchall()
    return list(rows)


def count_uploads_since(since: datetime) -> int:
    """Count uploaded clips since an instant."""
    with connect() as conn:
        row = conn.execute(
            "SELECT count(*) FROM clips WHERE status = 'uploaded' AND uploaded_at >= %s",
            (since,),
        ).fetchone()
    return int(row[0]) if row else 0


def latest_upload_at() -> datetime | None:
    """Return the most recent successful upload time."""
    with connect() as conn:
        row = conn.execute(
            "SELECT max(uploaded_at) FROM clips WHERE status = 'uploaded'"
        ).fetchone()
    return row[0] if row else None


def oldest_upload_since(since: datetime) -> datetime | None:
    """Return the oldest upload in the rolling window."""
    with connect() as conn:
        row = conn.execute(
            "SELECT min(uploaded_at) FROM clips WHERE status = 'uploaded' AND uploaded_at >= %s",
            (since,),
        ).fetchone()
    return row[0] if row else None


def mark_uploaded(clip_id: str, youtube_video_id: str) -> bool:
    """Mark an approved clip uploaded and record the upload time."""
    with connect() as conn:
        updated = conn.execute(
            """
            UPDATE clips
            SET status = 'uploaded', youtube_video_id = %s,
                uploaded_at = now(), updated_at = now()
            WHERE id = %s AND status = 'approved'
            """,
            (youtube_video_id, clip_id),
        ).rowcount == 1
    return updated


def count_auto_rendered_since(since: datetime) -> int:
    """Count successful auto-renders since an instant."""
    with connect() as conn:
        row = conn.execute(
            "SELECT count(*) FROM clips WHERE auto_rendered_at >= %s",
            (since,),
        ).fetchone()
    return int(row[0]) if row else 0


def mark_auto_rendered(clip_id: str) -> bool:
    """Record that a clip was rendered by the auto-render path."""
    with connect() as conn:
        updated = conn.execute(
            "UPDATE clips SET auto_rendered_at = now() WHERE id = %s",
            (clip_id,),
        ).rowcount == 1
    return updated


def get_stale_clips(stale_after_hours: int, limit: int = 100) -> list[dict[str, Any]]:
    """Return approved/rendered clips older than the freshness cutoff."""
    with connect(row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT id, status, blob_url, thumb_url, clip_created_at
            FROM clips
            WHERE status IN ('approved', 'rendered')
              AND clip_created_at IS NOT NULL
              AND clip_created_at < now() - make_interval(hours => %s)
            ORDER BY clip_created_at ASC
            LIMIT %s
            """,
            (stale_after_hours, limit),
        ).fetchall()
    return list(rows)


def mark_stale(clip_id: str, *, clear_blobs: bool = True) -> bool:
    """Reject a stale clip, optionally clearing its blob URLs."""
    fields = "status = 'rejected', error = 'stale', updated_at = now()"
    if clear_blobs:
        fields += ", blob_url = NULL, thumb_url = NULL"
    with connect() as conn:
        updated = conn.execute(
            f"UPDATE clips SET {fields} WHERE id = %s",
            (clip_id,),
        ).rowcount == 1
    logger.info("clip %s marked stale", clip_id)
    return updated


def get_stale_rejected_with_blobs(limit: int = 100) -> list[dict[str, Any]]:
    """Return rejected stale clips whose blob cleanup previously failed."""
    with connect(row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT id, blob_url, thumb_url FROM clips
            WHERE status = 'rejected' AND error = 'stale'
              AND (blob_url IS NOT NULL OR thumb_url IS NOT NULL)
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return list(rows)


def recover_stale_downloads(minutes: int = 30) -> int:
    """Mark abandoned download rows timed out so they can be retried."""
    with connect() as conn:
        count = conn.execute(
            """
            UPDATE clips
            SET status = 'failed', error = 'timed out', updated_at = now()
            WHERE status = 'downloaded'
              AND updated_at < now() - make_interval(mins => %s)
            """,
            (minutes,),
        ).rowcount
    if count:
        logger.warning("recovered %d stale downloaded clip(s)", count)
    return count


def get_fetch_state() -> datetime | None:
    """Return the last successful fetch time."""
    with connect() as conn:
        row = conn.execute(
            "SELECT last_fetch_at FROM fetch_state WHERE id = TRUE"
        ).fetchone()
    return row[0] if row else None


def set_fetch_state(when: datetime | None = None) -> None:
    """Record a successful fetch time."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO fetch_state (id, last_fetch_at, updated_at)
            VALUES (TRUE, COALESCE(%s, now()), now())
            ON CONFLICT (id) DO UPDATE
            SET last_fetch_at = COALESCE(EXCLUDED.last_fetch_at, now()),
                updated_at = now()
            """,
            (when,),
        )



def clear_blob_urls(clip_id: str) -> bool:
    """Clear blob URLs after a successful cleanup retry."""
    with connect() as conn:
        updated = conn.execute(
            "UPDATE clips SET blob_url = NULL, thumb_url = NULL, updated_at = now() WHERE id = %s",
            (clip_id,),
        ).rowcount == 1
    return updated



def get_clip(clip_id: str) -> dict[str, Any] | None:
    """Return one clip row."""
    with connect(row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT * FROM clips WHERE id = %s LIMIT 1", (clip_id,)
        ).fetchone()
    return dict(row) if row else None



@contextmanager
def advisory_lock(key: int):
    """Hold a Postgres advisory lock for the duration of a context."""
    conn = connect()
    acquired = False
    try:
        row = conn.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()
        acquired = bool(row and row[0])
        if acquired:
            conn.commit()
        yield acquired
    finally:
        try:
            if acquired:
                conn.execute("SELECT pg_advisory_unlock(%s)", (key,))
                conn.commit()
        finally:
            conn.close()


@contextmanager
def upload_lock():
    """Hold a Postgres advisory lock so upload jobs cannot overlap."""
    conn = connect()
    acquired = False
    try:
        row = conn.execute("SELECT pg_try_advisory_lock(783421)").fetchone()
        acquired = bool(row and row[0])
        if acquired:
            conn.commit()
        yield acquired
    finally:
        try:
            if acquired:
                conn.execute("SELECT pg_advisory_unlock(783421)")
                conn.commit()
        finally:
            conn.close()



def get_automation_state() -> dict[str, Any] | None:
    """Return the single automation state row."""
    with connect(row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT * FROM automation_state WHERE id = TRUE LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def ensure_automation_state(
    launch_date: str,
    upload_cap: int,
    fetch_limit: int,
    render_limit: int,
) -> dict[str, Any]:
    """Create the automation row if needed and return it."""
    with connect(row_factory=dict_row) as conn:
        conn.execute(
            """
            INSERT INTO automation_state
                (id, launch_date, upload_cap, fetch_limit, render_limit)
            VALUES (TRUE, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                launch_date = EXCLUDED.launch_date,
                updated_at = now()
            """,
            (launch_date, upload_cap, fetch_limit, render_limit),
        )
        row = conn.execute(
            "SELECT * FROM automation_state WHERE id = TRUE"
        ).fetchone()
    if row is None:
        raise RuntimeError("automation_state row missing")
    return dict(row)


def set_automation_limits(
    upload_cap: int, fetch_limit: int, render_limit: int
) -> None:
    """Update the current automation caps."""
    with connect() as conn:
        conn.execute(
            """
            UPDATE automation_state
            SET upload_cap = %s, fetch_limit = %s, render_limit = %s,
                updated_at = now()
            WHERE id = TRUE
            """,
            (upload_cap, fetch_limit, render_limit),
        )


def record_upload_limit_error(kind: str) -> None:
    """Record a YouTube quota/upload-limit stop so ramp can freeze."""
    column = (
        "last_upload_limit_at"
        if kind == "upload_limit"
        else "last_quota_error_at"
    )
    with connect() as conn:
        conn.execute(
            f"UPDATE automation_state SET {column} = now(), updated_at = now() WHERE id = TRUE"
        )



def get_existing_clip_ids(clip_ids: list[str]) -> set[str]:
    """Return which clip ids already exist in the database."""
    cleaned = [str(clip_id) for clip_id in clip_ids if clip_id]
    if not cleaned:
        return set()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id FROM clips WHERE id = ANY(%s)", (cleaned,)
        ).fetchall()
    return {str(row[0]) for row in rows}


def set_clip_privacy(clip_id: str, privacy: str) -> bool:
    """Update a clip's stored YouTube privacy."""
    if privacy not in {"public", "unlisted", "private"}:
        raise ValueError(f"unknown privacy {privacy!r}")
    with connect() as conn:
        updated = conn.execute(
            "UPDATE clips SET yt_privacy = %s, updated_at = now() WHERE id = %s",
            (privacy, clip_id),
        ).rowcount == 1
    return updated


def get_recent_uploads(since: datetime, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent uploaded clips that still have a YouTube video id."""
    with connect(row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT id, streamer_login, youtube_video_id, uploaded_at
            FROM clips
            WHERE status = 'uploaded'
              AND youtube_video_id IS NOT NULL
              AND uploaded_at >= %s
            ORDER BY uploaded_at DESC
            LIMIT %s
            """,
            (since, limit),
        ).fetchall()
    return list(rows)


def mark_youtube_rejected(clip_id: str, reason: str) -> bool:
    """Move an uploaded clip to rejected after YouTube removes it."""
    with connect() as conn:
        updated = conn.execute(
            """
            UPDATE clips
            SET status = 'rejected', error = %s, updated_at = now()
            WHERE id = %s AND status = 'uploaded'
            """,
            (reason, clip_id),
        ).rowcount == 1
    if updated:
        logger.error("clip %s rejected by YouTube: %s", clip_id, reason)
    return updated


def pause_automation(hours: int) -> None:
    """Pause uploads for a number of hours after a policy rejection."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO automation_state (id, paused_until, updated_at)
            VALUES (TRUE, now() + make_interval(hours => %s), now())
            ON CONFLICT (id) DO UPDATE
            SET paused_until = EXCLUDED.paused_until, updated_at = now()
            """,
            (hours,),
        )
    logger.error("automation paused for %d hour(s)", hours)


def automation_paused(now: datetime | None = None) -> bool:
    """Return whether uploads are paused after a policy rejection."""
    with connect(row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT paused_until, now() AS current_time FROM automation_state WHERE id = TRUE"
        ).fetchone()
    if not row or row["paused_until"] is None:
        return False
    instant = now or row["current_time"]
    return row["paused_until"] > instant
