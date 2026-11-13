"""Optional integration test that needs a real DATABASE_URL."""

from __future__ import annotations

import os

import psycopg
import pytest

from clipmachine import db

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set"
    ),
]


def test_init_db_twice_and_verify_schema() -> None:
    """init_db is idempotent and creates the table plus both indexes."""
    db.init_db()
    db.init_db()

    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        table = conn.execute("SELECT to_regclass('public.clips')").fetchone()
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'clips'"
            ).fetchall()
        }

    assert table is not None and table[0] == "clips"
    assert {"clips_status_idx", "clips_streamer_login_idx"} <= indexes
