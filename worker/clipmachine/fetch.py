"""Fetch GTA clips from Twitch and store them as new rows."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from clipmachine import db
from clipmachine.config import Settings, Streamer, load_config
from clipmachine.models import NewClip
from clipmachine.reddit import run_reddit
from clipmachine.twitch import TwitchClient, TwitchError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    """Counts produced by one fetch run."""

    streamers_checked: int
    clips_found: int
    selected: int
    new_clips: int
    auto_render_ids: list[str] | None = None


def _as_int(value: Any) -> int:
    """Coerce a Twitch numeric value to int, defaulting to zero."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    """Coerce a Twitch numeric value to float, defaulting to zero."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a Twitch ISO timestamp into an aware datetime."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _keep(clip: dict[str, Any], game_id: str, settings: Settings) -> bool:
    """Return whether a raw clip passes the game, views, and duration filters."""
    return (
        clip.get("game_id") == game_id
        and _as_int(clip.get("view_count")) >= settings.min_views
        and _as_float(clip.get("duration")) <= settings.max_clip_seconds
    )


def _clip_login(clip: dict[str, Any]) -> str | None:
    """Extract the Twitch login from a clip URL or broadcaster name."""
    url = clip.get("url")
    if isinstance(url, str):
        path = [part for part in urlparse(url).path.split("/") if part]
        if len(path) >= 2 and path[1] == "clip":
            return path[0].lower()
    name = clip.get("broadcaster_name")
    if isinstance(name, str) and name.strip():
        return name.strip().lower()
    return None


def _language_ok(settings: Settings, clip: dict[str, Any]) -> bool:
    """Return whether a clip matches the requested category language."""
    wanted = settings.clip_language.strip().lower()
    if wanted in {"", "all"}:
        return True
    language = str(clip.get("language") or "").strip().lower()
    return language == wanted


def _to_new_clip(streamer: Streamer, clip: dict[str, Any]) -> NewClip | None:
    """Map a raw Twitch clip to a NewClip, or None when required fields are missing."""
    clip_id = clip.get("id")
    url = clip.get("url")
    if not isinstance(clip_id, str) or not clip_id:
        return None
    if not isinstance(url, str) or not url:
        return None
    title = clip.get("title")
    return NewClip(
        id=clip_id,
        streamer_login=streamer.twitch_login,
        streamer_name=streamer.name,
        clip_url=url,
        clip_title=title if isinstance(title, str) else None,
        view_count=_as_int(clip.get("view_count")),
        duration_s=_as_float(clip.get("duration")),
        clip_created_at=_parse_timestamp(clip.get("created_at")),
        thumbnail_url=(
            str(clip.get("thumbnail_url"))
            if clip.get("thumbnail_url")
            else None
        ),
    )


def _scheduled_interval_skip(settings: Settings) -> bool:
    """Return whether a scheduled fetch is inside the configured cooldown."""
    if os.environ.get("FORCE_FETCH", "").strip() == "1":
        return False
    if os.environ.get("GITHUB_EVENT_NAME", "") != "schedule":
        return False
    if settings.fetch_interval_minutes <= 0:
        return False
    last = db.get_fetch_state()
    if last is None:
        return False
    elapsed = datetime.now(timezone.utc) - last
    if elapsed < timedelta(minutes=settings.fetch_interval_minutes):
        logger.info(
            "fetch skipped: last fetch %.1f minutes ago (interval=%d)",
            elapsed.total_seconds() / 60,
            settings.fetch_interval_minutes,
        )
        return True
    return False


def _select_auto_render(
    settings: Settings, candidate_ids: list[str]
) -> list[str]:
    """Choose the hybrid auto-render set and write it for the workflow."""
    auto_file = os.environ.get("AUTO_RENDER_IDS_FILE", "").strip()
    if not auto_file:
        return []
    unique_ids = list(dict.fromkeys(candidate_ids))
    if not unique_ids:
        Path(auto_file).write_text("", encoding="utf-8")
        return []
    rows = db.get_new_clips_by_ids(unique_ids)
    if not rows:
        Path(auto_file).write_text("", encoding="utf-8")
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    used = db.count_auto_rendered_since(since)
    remaining = max(0, settings.auto_render_max_per_day - used)
    if remaining == 0:
        logger.info("auto render skipped: daily cap %d reached", settings.auto_render_max_per_day)
        Path(auto_file).write_text("", encoding="utf-8")
        return []

    reddit_rows = sorted(
        [row for row in rows if row.get("reddit_score") is not None],
        key=lambda row: (
            _as_int(row.get("reddit_score")),
            row.get("clip_created_at") or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    top_rows = sorted(
        rows, key=lambda row: _as_int(row.get("view_count")), reverse=True
    )[: settings.auto_render_top_n]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in [*reddit_rows, *top_rows]:
        clip_id = str(row.get("id") or "")
        if not clip_id or clip_id in seen:
            continue
        seen.add(clip_id)
        selected.append(row)
    limit = min(settings.auto_render_max_per_run, remaining)
    selected = selected[:limit]
    ids = [str(row["id"]) for row in selected]
    Path(auto_file).write_text("\n".join(ids), encoding="utf-8")
    logger.info(
        "auto render selected=%d remaining_daily=%d ids=%s",
        len(ids),
        remaining - len(ids),
        ",".join(ids),
    )
    return ids


def run_fetch(config_directory: Path | None = None) -> FetchResult:
    """Fetch, filter, and insert the top new clips from Twitch."""
    config = load_config(config_directory)
    settings = config.settings
    if _scheduled_interval_skip(settings):
        return FetchResult(0, 0, 0, 0, [])

    min_views_override = os.environ.get("MIN_VIEWS", "").strip()
    if min_views_override:
        try:
            min_views = int(min_views_override)
        except ValueError as exc:
            raise ValueError("MIN_VIEWS must be an integer") from exc
        if min_views < 0:
            raise ValueError("MIN_VIEWS must be >= 0")
        settings = replace(settings, min_views=min_views)

    scope_override = os.environ.get("CLIP_SCOPE", "").strip().lower()
    if scope_override:
        if scope_override not in {"category", "streamers"}:
            raise ValueError("CLIP_SCOPE must be category or streamers")
        settings = replace(settings, clip_scope=scope_override)

    client = TwitchClient()
    game_id = client.get_game_id(settings.game_name)
    logger.info(
        "fetch filters: scope=%s language=%s game=%s min_views=%d "
        "max_clip_seconds=%d lookback_hours=%d",
        settings.clip_scope,
        settings.clip_language,
        settings.game_name,
        settings.min_views,
        settings.max_clip_seconds,
        settings.lookback_hours,
    )

    ended_at = datetime.now(timezone.utc)
    started_at = ended_at - timedelta(hours=settings.lookback_hours)
    config_by_login = {
        streamer.twitch_login.lower(): streamer
        for streamer in config.streamers
    }
    user_ids: dict[str, str] = {}
    candidates: list[tuple[Streamer, dict[str, Any]]] = []

    if settings.clip_scope == "category":
        raw_clips = client.get_game_clips(game_id, started_at, ended_at)
        rejected_language = 0
        streamer_by_login: dict[str, Streamer] = {}
        all_logins: set[str] = set()
        for clip in raw_clips:
            if not _language_ok(settings, clip):
                rejected_language += 1
                continue
            if not _keep(clip, game_id, settings):
                continue
            login = _clip_login(clip)
            if not login:
                continue
            all_logins.add(login)
            streamer = config_by_login.get(login)
            if streamer is None:
                streamer = Streamer(
                    name=str(clip.get("broadcaster_name") or login),
                    twitch_login=login,
                )
                streamer_by_login.setdefault(login, streamer)
            broadcaster_id = clip.get("broadcaster_id")
            if isinstance(broadcaster_id, str) and broadcaster_id:
                user_ids[login] = broadcaster_id
            candidates.append((streamer, clip))
        logger.info(
            "category fetch summary: found=%d kept=%d rejected_language=%d "
            "streamers=%d",
            len(raw_clips),
            len(candidates),
            rejected_language,
            len(streamer_by_login),
        )
        streamers_checked = len(streamer_by_login)
    else:
        selected_logins = list(
            dict.fromkeys(
                login.strip().lower()
                for login in os.environ.get("STREAMERS", "").split(",")
                if login.strip()
            )
        )
        if selected_logins:
            unknown = [
                login for login in selected_logins if login not in config_by_login
            ]
            user_details: dict[str, dict[str, str]] = {}
            if unknown:
                try:
                    user_details = client.get_users(unknown)
                except TwitchError as exc:
                    logger.warning(
                        "could not look up selected streamers: %s", exc
                    )
            enabled = []
            for login in selected_logins:
                configured = config_by_login.get(login)
                if configured is not None:
                    enabled.append(configured)
                    continue
                display_name = (
                    user_details.get(login, {}).get("display_name") or login
                )
                enabled.append(Streamer(name=display_name, twitch_login=login))
        else:
            enabled = [
                streamer for streamer in config.streamers if streamer.enabled
            ]
        user_ids = client.get_user_ids(
            [streamer.twitch_login for streamer in enabled]
        )
        for streamer in enabled:
            broadcaster_id = user_ids.get(streamer.twitch_login.lower())
            if broadcaster_id is None:
                logger.warning(
                    "clip fetch streamer=%s skipped: Twitch user not found",
                    streamer.twitch_login,
                )
                continue
            clips = client.get_clips(broadcaster_id, started_at, ended_at)
            kept = [clip for clip in clips if _keep(clip, game_id, settings)]
            wrong_game = sum(
                1 for clip in clips if clip.get("game_id") != game_id
            )
            low_views = sum(
                1
                for clip in clips
                if _as_int(clip.get("view_count")) < settings.min_views
            )
            too_long = sum(
                1
                for clip in clips
                if _as_float(clip.get("duration"))
                > settings.max_clip_seconds
            )
            logger.info(
                "clip fetch streamer=%s clips=%d kept=%d rejected_game=%d "
                "rejected_views=%d rejected_duration=%d",
                streamer.twitch_login,
                len(clips),
                len(kept),
                wrong_game,
                low_views,
                too_long,
            )
            candidates.extend((streamer, clip) for clip in kept)
        streamers_checked = len(enabled)

    candidates.sort(
        key=lambda item: _as_int(item[1].get("view_count")), reverse=True
    )
    selected = candidates[: settings.max_clips_per_run]

    new_clips = 0
    inserted_ids: list[str] = []
    for streamer, clip in selected:
        new_clip = _to_new_clip(streamer, clip)
        if new_clip is None:
            logger.warning(
                "clip fetch streamer=%s skipped malformed clip %r",
                streamer.twitch_login,
                clip.get("id"),
            )
            continue
        try:
            inserted = db.upsert_new_clip(new_clip)
        except Exception:
            logger.exception("clip %s failed to insert", new_clip.id)
            continue
        if inserted:
            inserted_ids.append(new_clip.id)
        new_clips += int(inserted)

    reddit_ids: list[str] = []
    try:
        reddit_ids = run_reddit(
            settings,
            client,
            game_id=game_id,
            user_ids=user_ids,
        )
    except Exception:
        logger.exception("Reddit discovery failed; continuing with Twitch only")

    auto_ids = _select_auto_render(settings, [*inserted_ids, *reddit_ids])

    if os.environ.get("GITHUB_EVENT_NAME"):
        try:
            db.set_fetch_state()
        except Exception:
            logger.exception("could not record fetch state")

    logger.info(
        "fetch summary: scope=%s streamers=%d clips_found=%d selected=%d "
        "new=%d min_views=%d auto_render=%d",
        settings.clip_scope,
        streamers_checked,
        len(candidates),
        len(selected),
        new_clips,
        settings.min_views,
        len(auto_ids),
    )
    return FetchResult(
        streamers_checked=streamers_checked,
        clips_found=len(candidates),
        selected=len(selected),
        new_clips=new_clips,
        auto_render_ids=auto_ids,
    )
