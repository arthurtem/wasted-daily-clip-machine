"""Tests for the Twitch client with fully mocked HTTP."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from clipmachine.twitch import HELIX_BASE, TOKEN_URL, TwitchClient, TwitchError


class FakeClock:
    """A controllable monotonic-ish clock for token expiry tests."""

    def __init__(self, now: float = 1000.0) -> None:
        """Initialize the clock at a fixed time."""
        self.now = now

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now


def _client(clock: FakeClock | None = None, sleep=None) -> TwitchClient:
    """Build a client with explicit test credentials."""
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    if sleep is not None:
        kwargs["sleep"] = sleep
    return TwitchClient(
        client_id="test-client", client_secret="test-secret", **kwargs
    )


@responses.activate
def test_token_is_cached() -> None:
    """Two token requests reuse the in-memory token."""
    responses.post(TOKEN_URL, json={"access_token": "tok", "expires_in": 3600})
    client = _client()

    assert client.get_app_token() == "tok"
    assert client.get_app_token() == "tok"
    assert len(responses.calls) == 1


@responses.activate
def test_token_is_refreshed_after_expiry() -> None:
    """An expired cached token triggers a new token request."""
    responses.post(TOKEN_URL, json={"access_token": "one", "expires_in": 120})
    responses.post(TOKEN_URL, json={"access_token": "two", "expires_in": 120})
    clock = FakeClock(0.0)
    client = _client(clock=clock)

    assert client.get_app_token() == "one"
    clock.now = 120.0
    assert client.get_app_token() == "two"
    assert len(responses.calls) == 2


@responses.activate
def test_get_clips_follows_pagination() -> None:
    """get_clips requests a second page when a cursor is returned."""
    responses.post(TOKEN_URL, json={"access_token": "tok", "expires_in": 3600})
    clips_url = f"{HELIX_BASE}/clips"
    responses.get(
        clips_url,
        json={"data": [{"id": "first"}], "pagination": {"cursor": "abc"}},
    )
    responses.get(
        clips_url,
        json={"data": [{"id": "second"}], "pagination": {}},
    )
    client = _client()
    started = datetime(2026, 11, 13, tzinfo=timezone.utc)
    ended = datetime(2026, 11, 14, tzinfo=timezone.utc)

    clips = client.get_clips("123", started, ended)

    assert [clip["id"] for clip in clips] == ["first", "second"]
    assert len(responses.calls) == 3
    first_query = parse_qs(urlparse(responses.calls[1].request.url).query)
    second_query = parse_qs(urlparse(responses.calls[2].request.url).query)
    assert first_query["first"] == ["100"]
    assert first_query["broadcaster_id"] == ["123"]
    assert second_query["after"] == ["abc"]


@responses.activate
def test_retries_once_after_429() -> None:
    """A 429 waits for Ratelimit-Reset and retries the request once."""
    responses.post(TOKEN_URL, json={"access_token": "tok", "expires_in": 3600})
    games_url = f"{HELIX_BASE}/games"
    responses.get(games_url, status=429, headers={"Ratelimit-Reset": "1010"})
    responses.get(games_url, json={"data": [{"id": "456", "name": "GTA"}]})
    clock = FakeClock(1000.0)
    sleeps: list[float] = []
    client = _client(clock=clock, sleep=sleeps.append)

    assert client.get_game_id("GTA") == "456"
    assert sleeps == [10.0]
    assert len(responses.calls) == 3


@responses.activate
def test_refreshes_token_once_after_401() -> None:
    """A 401 refreshes the token and retries with the new one."""
    responses.post(TOKEN_URL, json={"access_token": "one", "expires_in": 3600})
    responses.post(TOKEN_URL, json={"access_token": "two", "expires_in": 3600})
    games_url = f"{HELIX_BASE}/games"
    responses.get(games_url, status=401, json={"message": "unauthorized"})
    responses.get(games_url, json={"data": [{"id": "456", "name": "GTA"}]})
    client = _client()

    assert client.get_game_id("GTA") == "456"
    assert len(responses.calls) == 4
    assert responses.calls[1].request.headers["Authorization"] == "Bearer one"
    assert responses.calls[3].request.headers["Authorization"] == "Bearer two"


@responses.activate
def test_get_game_id_not_found() -> None:
    """An empty games response raises a clear error."""
    responses.post(TOKEN_URL, json={"access_token": "tok", "expires_in": 3600})
    responses.get(f"{HELIX_BASE}/games", json={"data": []})

    with pytest.raises(TwitchError, match="game not found"):
        _client().get_game_id("Nonexistent Game")


@responses.activate
def test_get_user_ids_returns_lowercase_mapping() -> None:
    """User logins are mapped to ids using lowercase keys."""
    responses.post(TOKEN_URL, json={"access_token": "tok", "expires_in": 3600})
    responses.get(
        f"{HELIX_BASE}/users",
        json={
            "data": [
                {"id": "1", "login": "kaicenat"},
                {"id": "2", "login": "xQc"},
            ]
        },
    )

    mapping = _client().get_user_ids(["KaiCenat", "xQc", "missing"])

    assert mapping == {"kaicenat": "1", "xqc": "2"}


@responses.activate
def test_get_user_ids_chunks_at_100() -> None:
    """More than 100 logins are split across multiple requests."""
    responses.post(TOKEN_URL, json={"access_token": "tok", "expires_in": 3600})
    responses.get(f"{HELIX_BASE}/users", json={"data": []})
    responses.get(f"{HELIX_BASE}/users", json={"data": []})
    logins = [f"streamer{i}" for i in range(101)]

    _client().get_user_ids(logins)

    user_calls = [
        call for call in responses.calls if "/users" in call.request.url
    ]
    assert len(user_calls) == 2


@responses.activate
def test_non_success_status_raises() -> None:
    """A server error surfaces as a TwitchError."""
    responses.post(TOKEN_URL, json={"access_token": "tok", "expires_in": 3600})
    responses.get(f"{HELIX_BASE}/games", status=500, body="boom")

    with pytest.raises(TwitchError, match="500"):
        _client().get_game_id("GTA")


def test_missing_credentials_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client refuses to start without Twitch credentials."""
    monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)

    with pytest.raises(TwitchError, match="TWITCH_CLIENT_ID"):
        TwitchClient()
