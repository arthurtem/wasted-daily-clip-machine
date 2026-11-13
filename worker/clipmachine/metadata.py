"""Build YouTube title, description, and tags for a clip."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from clipmachine.hook import make_hook

TITLE_LIMIT = 100


@dataclass(frozen=True)
class YouTubeMetadata:
    """The YouTube fields stored on a rendered clip."""

    title: str
    description: str
    tags: list[str]


def build_youtube_metadata(clip: Mapping[str, Any]) -> YouTubeMetadata:
    """Build the YouTube title, description, and tags for a clip."""
    hook = make_hook(clip)
    streamer_name = str(clip.get("streamer_name") or "Streamer")
    streamer_login = str(clip.get("streamer_login") or "")
    clip_url = str(clip.get("clip_url") or "")

    title = f"{hook} | {streamer_name} GTA 6 #shorts"[:TITLE_LIMIT].rstrip()
    description = "\n".join(
        [
            f"{streamer_name} live on Twitch: https://twitch.tv/{streamer_login}",
            f"Original clip: {clip_url}",
            f"#GTA6 #GTAVI #{streamer_login} #shorts",
        ]
    )
    tags = [
        "GTA 6",
        "GTA VI",
        streamer_name,
        "Grand Theft Auto 6",
        "shorts",
    ]
    return YouTubeMetadata(title=title, description=description, tags=tags)
