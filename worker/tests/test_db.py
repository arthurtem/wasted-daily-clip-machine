"""Tests for database access with a fake psycopg connection."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from psycopg.types.json import Jsonb

from clipmachine import db
from clipmachine.models import NewClip


class FakeCursor:
    """Record executed statements and return canned rows."""

    def __init__(self, rowcount: int, rows: list[dict[str, Any]]) -> None:
        """Initialize a cursor with a rowcount and result rows."""
        self.rowcount = rowcount
        self._rows = rows
        self.executions: list[tuple[Any, Any]] = []

    def fetchall(self) -> list[dict[str, Any]]:
        """Return the canned rows."""
        return self._rows


class FakeConnection:
    """Minimal connection context manager that records executions."""

    def __init__(self, rowcount: int, rows: list[dict[str, Any]]) -> None:
        """Initialize a connection backed by a fake cursor."""
        self.cursor = FakeCursor(rowcount, rows)
        self.exited = False

    def __enter__(self) -> FakeConnection:
        """Enter the connection context."""
        return self

    def __exit__(self, *exc_info: object) -> bool:
        """Leave the connection context without suppressing errors."""
        self.exited = True
        return False

    def execute(self, query: Any, params: Any = None) -> FakeCursor:
        """Record a statement and return the fake cursor."""
        self.cursor.executions.append((query, params))
        return self.cursor


class FakeDriver:
    """Stand-in for psycopg.connect that records every connection."""

    def __init__(self) -> None:
        """Initialize a driver with successful defaults."""
        self.rowcount = 1
        self.rows: list[dict[str, Any]] = []
        self.connections: list[FakeConnection] = []

    def connect(self, dsn: str, **kwargs: Any) -> FakeConnection:
        """Create and record a fake connection."""
        connection = FakeConnection(self.rowcount, self.rows)
        self.connections.append(connection)
        return connection

    def executables(self) -> list[tuple[Any, Any]]:
        """Flatten all recorded executions across connections."""
        return [
            execution
            for connection in self.connections
            for execution in connection.cursor.executions
        ]


@pytest.fixture
def fake_driver(monkeypatch: pytest.MonkeyPatch) -> FakeDriver:
    """Patch psycopg.connect and provide a dummy DATABASE_URL."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.test/wasted")
    driver = FakeDriver()
    monkeypatch.setattr(db.psycopg, "connect", driver.connect)
    return driver


def test_database_url_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing DATABASE_URL raises a clear configuration error."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(db.DatabaseError, match="DATABASE_URL is not set"):
        db.init_db()


def test_init_db_applies_migrations_idempotently(fake_driver: FakeDriver) -> None:
    """init_db runs the idempotent migration SQL on every call."""
    db.init_db()
    db.init_db()

    assert len(fake_driver.connections) == 2
    for connection in fake_driver.connections:
        assert connection.exited is True
    query = str(fake_driver.executables()[0][0])
    assert "CREATE TABLE IF NOT EXISTS clips" in query
    assert "CREATE INDEX IF NOT EXISTS clips_status_idx" in query
    assert "CREATE INDEX IF NOT EXISTS clips_streamer_login_idx" in query


def test_init_db_requires_migrations(tmp_path: Path) -> None:
    """An empty migrations directory is an error."""
    with pytest.raises(db.DatabaseError, match="no migrations found"):
        db.init_db(tmp_path)


def test_upsert_new_clip_inserts(fake_driver: FakeDriver) -> None:
    """A new clip is inserted with ON CONFLICT DO NOTHING."""
    clip = NewClip(
        id="ClipAbc123",
        streamer_login="kaicenat",
        streamer_name="Kai Cenat",
        clip_url="https://clips.twitch.tv/ClipAbc123",
        clip_title="Insane moment",
        view_count=1234,
        duration_s=28.5,
        clip_created_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
    )

    inserted = db.upsert_new_clip(clip)

    assert inserted is True
    query, params = fake_driver.executables()[0]
    assert "ON CONFLICT (id) DO NOTHING" in str(query)
    assert params[0] == "ClipAbc123"
    assert params[1] == "twitch"
    assert params[2] == "kaicenat"
    assert params[8] == datetime(2026, 11, 13, tzinfo=timezone.utc)


def test_upsert_new_clip_reports_existing(fake_driver: FakeDriver) -> None:
    """An existing clip id returns False."""
    fake_driver.rowcount = 0
    clip = NewClip(
        id="ClipAbc123",
        streamer_login="xqc",
        streamer_name="xQc",
        clip_url="https://clips.twitch.tv/ClipAbc123",
    )

    assert db.upsert_new_clip(clip) is False


def test_get_clips_uses_parameters(fake_driver: FakeDriver) -> None:
    """get_clips filters by status and limit with bound parameters."""
    fake_driver.rows = [{"id": "one"}, {"id": "two"}]

    rows = db.get_clips("rendered", 5)

    assert rows == [{"id": "one"}, {"id": "two"}]
    query, params = fake_driver.executables()[0]
    assert "WHERE status = %s" in str(query)
    assert params == ("rendered", 5)


def test_get_clips_rejects_unknown_status(fake_driver: FakeDriver) -> None:
    """Unknown statuses are rejected before touching the database."""
    with pytest.raises(ValueError, match="unknown clip status"):
        db.get_clips("archived", 5)

    assert fake_driver.connections == []


def test_set_status_updates_fields(fake_driver: FakeDriver) -> None:
    """set_status writes status, error, layout, and whitelisted fields."""
    updated = db.set_status(
        "ClipAbc123",
        "rendered",
        layout={"facecam": "top-left"},
        yt_title="Kai goes wild",
        yt_tags=["gta", "twitch"],
    )

    assert updated is True
    query, params = fake_driver.executables()[0]
    text = query.as_string(None)
    assert "status = %s" in text
    assert "error = %s" in text
    assert "updated_at = now()" in text
    assert '"layout" = %s' in text
    assert '"yt_title" = %s' in text
    assert '"yt_tags" = %s' in text
    assert params[0] == "rendered"
    assert params[1] is None
    assert isinstance(params[2], Jsonb)
    assert params[2].obj == {"facecam": "top-left"}
    assert params[3] == ["gta", "twitch"]
    assert params[4] == "Kai goes wild"
    assert params[-1] == "ClipAbc123"


def test_set_status_returns_false_for_missing_clip(fake_driver: FakeDriver) -> None:
    """A missing clip returns False instead of raising."""
    fake_driver.rowcount = 0

    assert db.set_status("missing", "failed", error="boom") is False


def test_set_status_rejects_unknown_status(fake_driver: FakeDriver) -> None:
    """Only the documented clip statuses are accepted."""
    with pytest.raises(ValueError, match="unknown clip status"):
        db.set_status("ClipAbc123", "archived")

    assert fake_driver.connections == []


def test_set_status_rejects_unknown_field(fake_driver: FakeDriver) -> None:
    """Arbitrary column names are rejected."""
    with pytest.raises(ValueError, match="unknown clip fields: drop_table"):
        db.set_status("ClipAbc123", "failed", drop_table="clips")

    assert fake_driver.connections == []
