"""Tests for the fetch pipeline with a fake Twitch client and database."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import pytest

from clipmachine import fetch
from clipmachine.config import AppConfig, Settings, Streamer
from clipmachine.models import NewClip


class FakeClient:
    """Fake TwitchClient returning canned ids and clips."""

    def __init__(
        self,
        game_id: str,
        user_ids: dict[str, str],
        clips_by_broadcaster: dict[str, list[dict[str, Any]]],
        display_names: dict[str, str] | None = None,
    ) -> None:
        """Store the canned responses for a fetch run."""
        self.game_id = game_id
        self.user_ids = user_ids
        self.clips_by_broadcaster = clips_by_broadcaster
        self.display_names = display_names or {}
        self.requested_logins: list[str] = []
        self.requested_user_lookups: list[str] = []
        self.clips_calls: list[str] = []
        self.game_clips: list[dict[str, Any]] = []

    def get_game_id(self, name: str) -> str:
        """Return the canned game id."""
        return self.game_id

    def get_user_ids(self, logins: list[str]) -> dict[str, str]:
        """Record the requested logins and return the canned mapping."""
        self.requested_logins = list(logins)
        return self.user_ids

    def get_users(self, logins: list[str]) -> dict[str, dict[str, str]]:
        """Return canned id and display name details for logins."""
        self.requested_user_lookups.extend(logins)
        return {
            login: {
                "id": self.user_ids.get(login, ""),
                "display_name": self.display_names.get(login, login),
            }
            for login in logins
        }

    def get_clips(
        self, broadcaster_id: str, started_at: datetime, ended_at: datetime
    ) -> list[dict[str, Any]]:
        """Record the broadcaster and return its canned clips."""
        self.clips_calls.append(broadcaster_id)
        return self.clips_by_broadcaster.get(broadcaster_id, [])

    def get_game_clips(
        self, game_id: str, started_at: datetime, ended_at: datetime
    ) -> list[dict[str, Any]]:
        """Return canned category clips."""
        return self.game_clips


def make_config(
    streamers: list[Streamer], **overrides: Any
) -> AppConfig:
    """Build an AppConfig with predictable GTA V settings."""
    settings = Settings(
        game_name="Grand Theft Auto V",
        lookback_hours=24,
        min_views=1000,
        max_clips_per_run=10,
        max_clip_seconds=60,
        uploads_per_run=2,
    )
    return AppConfig(
        streamers=tuple(streamers), settings=replace(settings, **overrides)
    )


def make_clip(
    clip_id: str,
    views: int = 5000,
    duration: float = 30.0,
    game_id: str = "gta5",
) -> dict[str, Any]:
    """Build a raw Twitch clip payload."""
    return {
        "id": clip_id,
        "url": f"https://clips.twitch.tv/{clip_id}",
        "title": f"Title {clip_id}",
        "view_count": views,
        "duration": duration,
        "game_id": game_id,
        "created_at": "2026-11-13T10:00:00Z",
    }


def install(
    monkeypatch: pytest.MonkeyPatch,
    config: AppConfig,
    client: FakeClient,
    existing_ids: set[str] | None = None,
) -> list[NewClip]:
    """Patch config, Twitch, and upsert calls; return recorded upserts."""
    upserts: list[NewClip] = []
    existing = set(existing_ids or ())

    def fake_upsert(clip: NewClip) -> bool:
        """Record an upsert and simulate an existing row."""
        upserts.append(clip)
        return clip.id not in existing

    monkeypatch.setattr(fetch, "load_config", lambda directory=None: config)
    monkeypatch.setattr(fetch, "TwitchClient", lambda: client)
    monkeypatch.setattr(fetch.db, "upsert_new_clip", fake_upsert)
    return upserts


def test_filters_sort_and_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only matching clips survive and are inserted highest views first."""
    streamers = [
        Streamer(name="Kai Cenat", twitch_login="kaicenat"),
        Streamer(name="xQc", twitch_login="xqc"),
        Streamer(name="Disabled", twitch_login="disabled", enabled=False),
    ]
    client = FakeClient(
        game_id="gta5",
        user_ids={"kaicenat": "1001", "xqc": "1002"},
        clips_by_broadcaster={
            "1001": [
                make_clip("keep-a", views=9000),
                make_clip("wrong-game", views=9000, game_id="other"),
                make_clip("low-views", views=500),
                make_clip("too-long", views=9000, duration=90.0),
            ],
            "1002": [
                make_clip("keep-b", views=12000),
                make_clip("keep-c", views=3000),
            ],
        },
    )
    upserts = install(monkeypatch, make_config(streamers), client)

    result = fetch.run_fetch()

    assert client.requested_logins == ["kaicenat", "xqc"]
    assert client.clips_calls == ["1001", "1002"]
    assert [clip.id for clip in upserts] == ["keep-b", "keep-a", "keep-c"]
    assert result.streamers_checked == 2
    assert result.clips_found == 3
    assert result.selected == 3
    assert result.new_clips == 3
    assert upserts[1].streamer_name == "Kai Cenat"
    assert upserts[1].view_count == 9000
    assert upserts[1].duration_s == 30.0
    assert upserts[1].clip_created_at == datetime(
        2026, 11, 13, 10, tzinfo=timezone.utc
    )


def test_selection_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_clips_per_run limits how many clips are upserted."""
    streamers = [Streamer(name="Kai Cenat", twitch_login="kaicenat")]
    client = FakeClient(
        game_id="gta5",
        user_ids={"kaicenat": "1001"},
        clips_by_broadcaster={
            "1001": [
                make_clip("low", views=2000),
                make_clip("high", views=9000),
            ]
        },
    )
    upserts = install(
        monkeypatch, make_config(streamers, max_clips_per_run=1), client
    )

    result = fetch.run_fetch()

    assert result.clips_found == 2
    assert result.selected == 1
    assert [clip.id for clip in upserts] == ["high"]


def test_existing_ids_are_not_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    """An existing database id is skipped and not counted as new."""
    streamers = [Streamer(name="xQc", twitch_login="xqc")]
    client = FakeClient(
        game_id="gta5",
        user_ids={"xqc": "1002"},
        clips_by_broadcaster={
            "1002": [make_clip("old", views=9000), make_clip("fresh", views=8000)]
        },
    )
    upserts = install(
        monkeypatch, make_config(streamers), client, existing_ids={"old"}
    )

    result = fetch.run_fetch()

    assert len(upserts) == 2
    assert result.selected == 2
    assert result.new_clips == 1


def test_missing_user_skips_streamer(monkeypatch: pytest.MonkeyPatch) -> None:
    """A streamer without a resolved user id is skipped, not fatal."""
    streamers = [
        Streamer(name="Kai Cenat", twitch_login="kaicenat"),
        Streamer(name="xQc", twitch_login="xqc"),
    ]
    client = FakeClient(
        game_id="gta5",
        user_ids={"kaicenat": "1001"},
        clips_by_broadcaster={
            "1001": [make_clip("keep", views=9000)],
            "1002": [make_clip("never-fetched", views=9000)],
        },
    )
    upserts = install(monkeypatch, make_config(streamers), client)

    result = fetch.run_fetch()

    assert client.clips_calls == ["1001"]
    assert result.streamers_checked == 2
    assert result.new_clips == 1
    assert [clip.id for clip in upserts] == ["keep"]


def test_malformed_clip_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clip without id or url is logged and skipped without failing the run."""
    streamers = [Streamer(name="xQc", twitch_login="xqc")]
    malformed = make_clip("ignored")
    malformed["id"] = None
    client = FakeClient(
        game_id="gta5",
        user_ids={"xqc": "1002"},
        clips_by_broadcaster={"1002": [malformed, make_clip("good", views=9000)]},
    )
    upserts = install(monkeypatch, make_config(streamers), client)

    result = fetch.run_fetch()

    assert [clip.id for clip in upserts] == ["good"]
    assert result.new_clips == 1


def test_streamer_filter_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """STREAMERS restricts the fetch to the requested logins."""
    monkeypatch.setenv("STREAMERS", "xqc")
    streamers = [
        Streamer(name="Kai Cenat", twitch_login="kaicenat"),
        Streamer(name="xQc", twitch_login="xqc"),
    ]
    client = FakeClient(
        game_id="gta5",
        user_ids={"kaicenat": "1001", "xqc": "1002"},
        clips_by_broadcaster={"1002": [make_clip("keep", views=9000)]},
    )
    install(monkeypatch, make_config(streamers), client)

    result = fetch.run_fetch()

    assert client.requested_logins == ["xqc"]
    assert client.clips_calls == ["1002"]
    assert result.streamers_checked == 1
    assert result.new_clips == 1


def test_min_views_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """MIN_VIEWS lets a test run include low-view clips."""
    monkeypatch.setenv("MIN_VIEWS", "0")
    streamers = [Streamer(name="xQc", twitch_login="xqc")]
    client = FakeClient(
        game_id="gta5",
        user_ids={"xqc": "1002"},
        clips_by_broadcaster={"1002": [make_clip("low", views=5)]},
    )
    upserts = install(
        monkeypatch,
        make_config(streamers, min_views=1000),
        client,
    )

    result = fetch.run_fetch()

    assert result.new_clips == 1
    assert [clip.id for clip in upserts] == ["low"]


def test_selected_streamer_outside_config_uses_twitch_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A searched streamer not in streamers.yaml is fetched with its display name."""
    monkeypatch.setenv("STREAMERS", "newstreamer")
    client = FakeClient(
        game_id="gta5",
        user_ids={"newstreamer": "9001"},
        clips_by_broadcaster={"9001": [make_clip("new", views=9000)]},
        display_names={"newstreamer": "New Streamer"},
    )
    upserts = install(
        monkeypatch,
        make_config([Streamer(name="xQc", twitch_login="xqc")]),
        client,
    )

    result = fetch.run_fetch()

    assert client.requested_user_lookups == ["newstreamer"]
    assert client.requested_logins == ["newstreamer"]
    assert result.new_clips == 1
    assert upserts[0].streamer_name == "New Streamer"


def test_category_scope_filters_language_and_resolves_logins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Category mode ignores streamers, filters language, and keeps top views."""
    streamers = [Streamer(name="Kai Cenat", twitch_login="kaicenat")]
    client = FakeClient(
        game_id="gta5",
        user_ids={},
        clips_by_broadcaster={},
    )
    client.game_clips = [
        {
            "id": "en-high",
            "url": "https://www.twitch.tv/englishguy/clip/en-high",
            "title": "English high",
            "view_count": 5000,
            "duration": 30,
            "game_id": "gta5",
            "language": "en",
            "created_at": "2026-11-13T10:00:00Z",
            "broadcaster_id": "2002",
            "broadcaster_name": "EnglishGuy",
        },
        {
            "id": "ja-high",
            "url": "https://www.twitch.tv/japaneseguy/clip/ja-high",
            "title": "Japanese high",
            "view_count": 9000,
            "duration": 30,
            "game_id": "gta5",
            "language": "ja",
            "created_at": "2026-11-13T10:00:00Z",
            "broadcaster_id": "2003",
            "broadcaster_name": "JapaneseGuy",
        },
        {
            "id": "en-low",
            "url": "https://www.twitch.tv/englishguy/clip/en-low",
            "title": "English low",
            "view_count": 3000,
            "duration": 30,
            "game_id": "gta5",
            "language": "en",
            "created_at": "2026-11-13T10:00:00Z",
            "broadcaster_id": "2002",
            "broadcaster_name": "EnglishGuy",
        },
    ]
    upserts = install(
        monkeypatch,
        make_config(
            streamers,
            clip_scope="category",
            clip_language="en",
            min_views=0,
        ),
        client,
    )

    result = fetch.run_fetch()

    assert [clip.id for clip in upserts] == ["en-high", "en-low"]
    assert upserts[0].streamer_login == "englishguy"
    assert result.streamers_checked == 1
    assert result.clips_found == 2
