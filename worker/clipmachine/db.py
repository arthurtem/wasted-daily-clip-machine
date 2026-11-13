"""Postgres access for clip rows and schema migrations."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
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
            view_count, duration_s, clip_created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
