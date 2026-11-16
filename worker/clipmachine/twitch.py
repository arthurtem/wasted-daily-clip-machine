"""Minimal Twitch Helix API client with token caching and retries."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX_BASE = "https://api.twitch.tv/helix"
REQUEST_TIMEOUT = 30.0
TOKEN_SAFETY_SECONDS = 60
MAX_USERS_PER_CALL = 100
CLIPS_PAGE_SIZE = 100


class TwitchError(RuntimeError):
    """Raised when a Twitch API call cannot be completed."""


def _rfc3339(value: datetime) -> str:
    """Format a datetime as UTC RFC3339 with seconds precision."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TwitchClient:
    """Small Helix client that caches its app token in memory."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        session: requests.Session | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        """Load credentials from arguments or the environment."""
        self.client_id = (client_id or os.environ.get("TWITCH_CLIENT_ID", "")).strip()
        self.client_secret = (
            client_secret or os.environ.get("TWITCH_CLIENT_SECRET", "")
        ).strip()
        if not self.client_id or not self.client_secret:
            raise TwitchError(
                "TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set"
            )
        self._session = session or requests.Session()
        self._clock = clock
        self._sleep = sleep
        self._timeout = timeout
        self._token: str | None = None
        self._expires_at = 0.0

    def get_app_token(self) -> str:
        """Return a cached app access token, requesting a new one when expired."""
        now = self._clock()
        if self._token is not None and now < self._expires_at:
            return self._token

        try:
            response = self._session.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise TwitchError(f"Twitch token request failed: {exc}") from exc

        if response.status_code != 200:
            raise TwitchError(
                f"Twitch token request failed ({response.status_code}): "
                f"{response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise TwitchError("Twitch token response was not JSON") from exc

        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise TwitchError("Twitch token response did not include access_token")

        try:
            expires_in = int(payload.get("expires_in", 3600))
        except (TypeError, ValueError):
            expires_in = 3600

        self._token = token
        self._expires_at = now + max(0, expires_in - TOKEN_SAFETY_SECONDS)
        logger.info("obtained Twitch app token (expires in %ss)", expires_in)
        return token

    def _rate_limit_delay(self, response: requests.Response) -> float:
        """Return seconds to wait until the Ratelimit-Reset header time."""
        reset = response.headers.get("Ratelimit-Reset")
        if reset is None:
            return 1.0
        try:
            return max(0.0, float(reset) - self._clock())
        except ValueError:
            return 1.0

    def _helix_get(
        self,
        path: str,
        params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """GET a Helix endpoint, retrying once on 401 and once on 429."""
        url = f"{HELIX_BASE}{path}"
        refreshed = False
        rate_limited = False
        while True:
            headers = {
                "Client-Id": self.client_id,
                "Authorization": f"Bearer {self.get_app_token()}",
            }
            try:
                response = self._session.get(
                    url, params=params, headers=headers, timeout=self._timeout
                )
            except requests.RequestException as exc:
                raise TwitchError(
                    f"Twitch request to {path} failed: {exc}"
                ) from exc

            if response.status_code == 401 and not refreshed:
                refreshed = True
                self._token = None
                logger.info("Twitch 401 on %s; refreshing token", path)
                continue
            if response.status_code == 429 and not rate_limited:
                rate_limited = True
                delay = self._rate_limit_delay(response)
                logger.info("Twitch 429 on %s; sleeping %.1fs", path, delay)
                self._sleep(delay)
                continue
            if response.status_code >= 400:
                raise TwitchError(
                    f"Twitch request to {path} failed ({response.status_code}): "
                    f"{response.text[:200]}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise TwitchError(
                    f"Twitch response from {path} was not JSON"
                ) from exc
            if not isinstance(payload, dict):
                raise TwitchError(
                    f"Twitch response from {path} was not a JSON object"
                )
            return payload

    def get_game_id(self, name: str) -> str:
        """Return the Twitch game id for a game name or raise a clear error."""
        payload = self._helix_get("/games", {"name": name})
        games = payload.get("data") or []
        if not games:
            raise TwitchError(f"Twitch game not found: {name!r}")
        game_id = games[0].get("id")
        if not isinstance(game_id, str) or not game_id:
            raise TwitchError(f"Twitch game {name!r} has no id")
        logger.info("resolved Twitch game %s -> %s", name, game_id)
        return game_id

    def get_user_ids(self, logins: Sequence[str]) -> dict[str, str]:
        """Return a lowercase-login to user-id map, at most 100 logins per call."""
        mapping: dict[str, str] = {}
        unique = sorted({login.lower() for login in logins if login})
        for start in range(0, len(unique), MAX_USERS_PER_CALL):
            chunk = unique[start : start + MAX_USERS_PER_CALL]
            params = [("login", login) for login in chunk]
            payload = self._helix_get("/users", params)
            for user in payload.get("data") or []:
                login = str(user.get("login", "")).lower()
                user_id = user.get("id")
                if login and isinstance(user_id, str) and user_id:
                    mapping[login] = user_id

        missing = [login for login in unique if login not in mapping]
        if missing:
            logger.warning(
                "Twitch returned no user for logins: %s", ", ".join(missing)
            )
        logger.info("resolved %d/%d Twitch user ids", len(mapping), len(unique))
        return mapping

    def get_users(
        self, logins: Sequence[str]
    ) -> dict[str, dict[str, str]]:
        """Return user id and display name for each Twitch login."""
        mapping: dict[str, dict[str, str]] = {}
        unique = sorted({login.lower() for login in logins if login})
        for start in range(0, len(unique), MAX_USERS_PER_CALL):
            chunk = unique[start : start + MAX_USERS_PER_CALL]
            params = [("login", login) for login in chunk]
            payload = self._helix_get("/users", params)
            for user in payload.get("data") or []:
                login = str(user.get("login", "")).lower()
                user_id = user.get("id")
                if not login or not isinstance(user_id, str) or not user_id:
                    continue
                mapping[login] = {
                    "id": user_id,
                    "display_name": str(
                        user.get("display_name") or login
                    ),
                }
        missing = [login for login in unique if login not in mapping]
        if missing:
            logger.warning(
                "Twitch returned no user for logins: %s", ", ".join(missing)
            )
        return mapping

    def get_clips(
        self, broadcaster_id: str, started_at: datetime, ended_at: datetime
    ) -> list[dict[str, Any]]:
        """Return every clip for a broadcaster in a window, following pagination."""
        clips: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            params: dict[str, Any] = {
                "broadcaster_id": broadcaster_id,
                "started_at": _rfc3339(started_at),
                "ended_at": _rfc3339(ended_at),
                "first": CLIPS_PAGE_SIZE,
            }
            if cursor:
                params["after"] = cursor
            payload = self._helix_get("/clips", params)
            clips.extend(payload.get("data") or [])
            cursor = (payload.get("pagination") or {}).get("cursor")
            if not cursor or cursor in seen_cursors:
                break
            seen_cursors.add(cursor)
        logger.info(
            "clip fetch broadcaster_id=%s window=%s..%s clips=%d",
            broadcaster_id,
            _rfc3339(started_at),
            _rfc3339(ended_at),
            len(clips),
        )
        return clips


    def get_clips_by_ids(self, clip_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Return Twitch clips by id, in chunks of 100."""
        clips: list[dict[str, Any]] = []
        unique = list(dict.fromkeys(
            str(clip_id) for clip_id in clip_ids if clip_id
        ))
        for start in range(0, len(unique), CLIPS_PAGE_SIZE):
            chunk = unique[start : start + CLIPS_PAGE_SIZE]
            params = [("id", clip_id) for clip_id in chunk]
            payload = self._helix_get("/clips", params)
            clips.extend(payload.get("data") or [])
        logger.info("clip lookup by id requested=%d found=%d", len(unique), len(clips))
        return clips
