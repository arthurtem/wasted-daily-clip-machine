"""Reddit trending discovery that resolves to original Twitch clips."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from clipmachine import db
from clipmachine.config import Settings, Streamer
from clipmachine.models import NewClip
from clipmachine.twitch import TwitchClient, TwitchError

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"
CLIP_ID_RE = re.compile(
    r"(?:clips\.twitch\.tv/|twitch\.tv/[^/]+/clip/)([A-Za-z0-9_-]+)"
)


class RedditError(RuntimeError):
    """Raised when Reddit discovery cannot be completed."""


def extract_clip_id(url: str | None) -> str | None:
    """Extract a Twitch clip slug from a Reddit post URL."""
    if not url:
        return None
    match = CLIP_ID_RE.search(url)
    return match.group(1) if match else None


def _parse_created(value: Any) -> datetime | None:
    """Parse a Twitch timestamp."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class RedditClient:
    """Small app-only Reddit API client."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.client_id = os.environ.get("REDDIT_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
        self.user_agent = (
            os.environ.get("REDDIT_USER_AGENT", "").strip()
            or "wasted-daily-clip-machine/0.1"
        )
        if not self.client_id or not self.client_secret:
            raise RedditError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set")
        self._session = session or requests.Session()
        self._token: str | None = None

    def _access_token(self) -> str:
        """Return an app-only access token."""
        if self._token:
            return self._token
        response = self._session.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self.user_agent},
            timeout=30,
        )
        if response.status_code != 200:
            raise RedditError(f"Reddit token failed ({response.status_code})")
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise RedditError("Reddit token response had no access_token")
        self._token = token
        return token

    def top_posts(self, subreddit: str, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch top posts from a subreddit for the day."""
        response = self._session.get(
            f"{API_BASE}/r/{subreddit}/top",
            params={"t": "day", "limit": limit, "raw_json": 1},
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "User-Agent": self.user_agent,
            },
            timeout=30,
        )
        if response.status_code != 200:
            raise RedditError(
                f"Reddit top failed for r/{subreddit} ({response.status_code})"
            )
        children = (response.json().get("data") or {}).get("children") or []
        return [child.get("data") or {} for child in children]


def _post_url(post: dict[str, Any]) -> str:
    """Return the external or Reddit URL for a post."""
    value = post.get("url_overridden_by_dest") or post.get("url")
    return str(value) if isinstance(value, str) else ""


def run_reddit(
    settings: Settings,
    twitch: TwitchClient,
    *,
    game_id: str,
    user_ids: dict[str, str],
) -> list[str]:
    """Enrich or import trending Twitch clips; return affected clip ids."""
    if not settings.reddit_enabled:
        return []
    try:
        client = RedditClient()
    except RedditError as exc:
        logger.warning("Reddit discovery disabled: %s", exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=settings.reddit_lookback_hours
    )
    candidates: list[dict[str, Any]] = []
    total_matched = 0
    for subreddit in settings.reddit_subreddits:
        try:
            posts = client.top_posts(subreddit)
        except (RedditError, requests.RequestException) as exc:
            logger.warning("Reddit scan failed for r/%s: %s", subreddit, exc)
            continue
        matched = 0
        for post in posts:
            created = post.get("created_utc")
            created_at = (
                datetime.fromtimestamp(float(created), tz=timezone.utc)
                if created is not None
                else None
            )
            if created_at is not None and created_at < cutoff:
                continue
            if post.get("over_18") or post.get("is_self"):
                continue
            score = int(post.get("score") or 0)
            if score < settings.reddit_min_score:
                continue
            clip_id = extract_clip_id(_post_url(post))
            if not clip_id:
                continue
            matched += 1
            total_matched += 1
            candidates.append(
                {
                    "post": post,
                    "clip_id": clip_id,
                    "score": score,
                    "subreddit": post.get("subreddit") or subreddit,
                    "url": f"https://www.reddit.com{post.get('permalink', '')}",
                }
            )
        logger.info(
            "reddit scan subreddit=%s posts=%d twitch_matches=%d",
            subreddit,
            len(posts),
            matched,
        )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    candidates = candidates[: settings.reddit_top_posts]
    if not candidates:
        logger.info("reddit summary: matched=0 selected=0")
        return []

    by_id: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        by_id.setdefault(candidate["clip_id"], candidate)
    try:
        raw_clips = twitch.get_clips_by_ids(list(by_id))
    except TwitchError as exc:
        logger.warning("could not resolve Reddit clips: %s", exc)
        return []

    id_to_login = {user_id: login for login, user_id in user_ids.items()}
    streamer_by_login: dict[str, Streamer] = {}
    affected: list[str] = []
    imported = enriched = 0
    for raw in raw_clips:
        clip_id = raw.get("id")
        candidate = by_id.get(str(clip_id)) if clip_id else None
        if candidate is None:
            continue
        if raw.get("game_id") != game_id:
            continue
        login = id_to_login.get(str(raw.get("broadcaster_id") or ""))
        if login is None:
            continue
        streamer = streamer_by_login.get(login)
        if streamer is None:
            name = str(raw.get("broadcaster_name") or login)
            streamer = Streamer(name=name, twitch_login=login)
            streamer_by_login[login] = streamer
        post = candidate["post"]
        if not raw.get("url"):
            continue
        new_clip = NewClip(
            id=str(clip_id),
            streamer_login=streamer.twitch_login,
            streamer_name=streamer.name,
            clip_url=str(raw.get("url") or ""),
            clip_title=raw.get("title") if isinstance(raw.get("title"), str) else None,
            view_count=int(raw.get("view_count") or 0),
            duration_s=float(raw.get("duration") or 0),
            clip_created_at=_parse_created(raw.get("created_at")),
            thumbnail_url=(
                str(raw.get("thumbnail_url")) if raw.get("thumbnail_url") else None
            ),
            reddit_score=candidate["score"],
            reddit_url=candidate["url"],
            reddit_id=str(post.get("id") or ""),
            reddit_subreddit=str(candidate["subreddit"]),
            reddit_comments=int(post.get("num_comments") or 0),
        )
        inserted = db.upsert_new_clip(new_clip)
        if inserted:
            imported += 1
            affected.append(new_clip.id)
        else:
            db.update_clip_metadata(
                new_clip.id,
                thumbnail_url=new_clip.thumbnail_url,
                reddit_score=new_clip.reddit_score,
                reddit_url=new_clip.reddit_url,
                reddit_id=new_clip.reddit_id,
                reddit_subreddit=new_clip.reddit_subreddit,
                reddit_comments=new_clip.reddit_comments,
            )
            existing = db.get_clip(new_clip.id)
            if existing and existing.get("status") == "new":
                affected.append(new_clip.id)
            enriched += 1
    logger.info(
        "reddit summary: matched=%d selected=%d resolved=%d imported=%d enriched=%d",
        total_matched,
        len(candidates),
        len(raw_clips),
        imported,
        enriched,
    )
    return affected
