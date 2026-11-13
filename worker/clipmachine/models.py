"""Typed values shared between the worker modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewClip:
    """A Twitch clip ready to be inserted as a ``new`` row."""

    id: str
    streamer_login: str
    streamer_name: str
    clip_url: str
    clip_title: str | None = None
    view_count: int | None = None
    duration_s: float | None = None
    clip_created_at: datetime | None = None
    source: str = "twitch"
