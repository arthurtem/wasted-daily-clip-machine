"""Tests for the command line interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from clipmachine import db, moderation
from clipmachine.cli import main
from clipmachine.config import AppConfig, Settings, Streamer
from clipmachine.facecam import Layout
from clipmachine.fetch import FetchResult
from conftest import write_config


def test_check_config_prints_streamers(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check-config prints all streamers and settings."""
    monkeypatch.setenv("CLIPMACHINE_CONFIG_DIR", str(config_dir))

    assert main(["check-config"]) == 0

    output = capsys.readouterr().out
    assert "Streamers (3):" in output
    assert output.count("  - ") == 3
    assert "kaicenat" in output
    assert "game_name: Grand Theft Auto VI" in output
    assert "uploads_per_run: 2" in output


def test_init_db_dispatches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """init-db calls db.init_db and reports success."""
    called: list[bool] = []

    def fake_init_db() -> None:
        """Record that init_db ran."""
        called.append(True)

    monkeypatch.setattr(db, "init_db", fake_init_db)

    assert main(["init-db"]) == 0
    assert called == [True]
    assert "Database schema is up to date." in capsys.readouterr().out


def test_check_config_reports_validation_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bad config exits 1 with a clear error message."""
    directory = write_config(
        tmp_path / "bad",
        streamers="""\
streamers:
  - name: "xQc"
    twitch_login: "xqc"
    enabled: true
    facecam_override: "middle"
""",
    )

    assert main(["--config-dir", str(directory), "check-config"]) == 1

    error = capsys.readouterr().err
    assert error.startswith("error:")
    assert "facecam_override" in error


def test_init_db_reports_missing_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing DATABASE_URL exits 1 without a traceback."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main(["init-db"]) == 1
    assert "DATABASE_URL is not set" in capsys.readouterr().err


def test_reddit_dispatches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], config_dir: Path
) -> None:
    """reddit runs the discovery helper with the configured streamers."""
    monkeypatch.setenv("CLIPMACHINE_CONFIG_DIR", str(config_dir))
    monkeypatch.setattr("clipmachine.cli.TwitchClient", lambda: object())
    monkeypatch.setattr(
        "clipmachine.cli.run_reddit", lambda *args, **kwargs: ["clip-a"]
    )
    # Avoid real Twitch calls by patching the tiny wrapper methods on a fake client.
    class FakeClient:
        def get_game_id(self, name: str) -> str:
            return "gta5"

        def get_user_ids(self, logins: list[str]) -> dict[str, str]:
            return {login: "1" for login in logins}

    monkeypatch.setattr("clipmachine.cli.TwitchClient", lambda: FakeClient())

    assert main(["reddit"]) == 0
    assert "Reddit affected 1 clip(s)." in capsys.readouterr().out


def test_fetch_dispatches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """fetch calls run_fetch and reports how many clips were added."""
    monkeypatch.setattr(
        "clipmachine.cli.run_fetch",
        lambda config_directory=None: FetchResult(
            streamers_checked=3, clips_found=5, selected=2, new_clips=2
        ),
    )

    assert main(["fetch"]) == 0
    assert "Fetched 2 new clip(s) from 3 streamer(s)." in capsys.readouterr().out


def _render_config() -> AppConfig:
    """Build a one-streamer config for render tests."""
    return AppConfig(
        streamers=(
            Streamer(
                name="xQc",
                twitch_login="xqc",
                facecam_box=(0.0, 0.2, 0.22, 0.3),
            ),
        ),
        settings=Settings(
            game_name="Grand Theft Auto V",
            lookback_hours=24,
            min_views=200,
            max_clips_per_run=10,
            max_clip_seconds=60,
            uploads_per_run=2,
        ),
    )


def _clip() -> dict[str, object]:
    """Build a database clip row for render tests."""
    return {
        "id": "c1",
        "streamer_login": "xqc",
        "streamer_name": "xQc",
        "clip_url": "https://clips.twitch.tv/c1",
        "clip_title": "xQc loses it completely",
    }


def test_render_runs_full_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """render detects, captions, renders, uploads, stores metadata, cleans up."""
    source = tmp_path / "c1" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"fake")
    ass_path = source.parent / "captions.ass"
    final_path = source.parent / "final.mp4"
    thumb_path = source.parent / "thumb.jpg"
    video_url = "https://blob.example/shorts/c1.mp4"
    thumb_url = "https://blob.example/shorts/c1.jpg"
    statuses: list[tuple[object, ...]] = []
    puts: list[tuple[Path, str]] = []

    def fake_status(
        clip_id: str, status: str, error: str | None = None, **fields: object
    ) -> bool:
        """Record a status update."""
        statuses.append((clip_id, status, error, fields))
        return True

    def fake_detect(
        path: Path,
        override: str | None,
        refine_cam_edges: bool = True,
        box_override: tuple[float, float, float, float] | None = None,
    ) -> Layout:
        """Return a verified cam_top layout."""
        return Layout(
            "cam_top", (0, 184, 400, 258), 1.0, None, "box", 1.0, False
        )

    def fake_render(
        source_path: Path,
        layout: Layout,
        out_path: Path,
        thumb_out: Path,
        ass: Path | None = None,
    ) -> None:
        """Record the render call without touching ffmpeg."""
        assert ass == ass_path

    def fake_put(path: Path, pathname: str) -> str:
        """Record an upload and return a fake public URL."""
        puts.append((path, pathname))
        return video_url if pathname.endswith(".mp4") else thumb_url

    monkeypatch.setattr(
        "clipmachine.cli.load_config", lambda directory=None: _render_config()
    )
    monkeypatch.setattr("clipmachine.cli.expire_stale", lambda hours: 0)
    monkeypatch.setattr("clipmachine.cli.recover_abandoned_renders", lambda: 0)
    monkeypatch.setattr(db, "get_new_clips", lambda limit: [_clip()])
    monkeypatch.setattr(db, "get_new_clips_by_ids", lambda ids: [_clip()])
    monkeypatch.setattr("clipmachine.cli.download_clip", lambda clip: source)
    monkeypatch.setattr("clipmachine.cli.detect_layout", fake_detect)
    monkeypatch.setattr(db, "set_status", fake_status)
    monkeypatch.setattr("clipmachine.cli.has_burned_captions", lambda path: False)
    monkeypatch.setattr(
        "clipmachine.cli.transcribe",
        lambda path: [{"word": "hello", "start": 0.0, "end": 0.4}],
    )
    monkeypatch.setattr(
        "clipmachine.cli.build_ass",
        lambda words, layout, path: ass_path,
    )
    monkeypatch.setattr("clipmachine.cli.render_final", fake_render)
    monkeypatch.setattr("clipmachine.cli.put_file", fake_put)
    monkeypatch.setattr("clipmachine.cli.delete_url", lambda url: None)
    monkeypatch.setattr(
        "clipmachine.cli.moderation.screen_clip",
        lambda video, thumb, settings: moderation.ClipScreening(
            moderation.CLEAN, 0.0
        ),
    )

    assert main(["render"]) == 0

    rendered = [status for status in statuses if status[1] == "rendered"]
    assert rendered
    fields = rendered[0][3]
    assert fields["blob_url"] == video_url
    assert fields["thumb_url"] == thumb_url
    assert fields["yt_title"].endswith("| xQc GTA 6 #shorts")
    assert fields["yt_tags"] == [
        "GTA 6",
        "GTA VI",
        "xQc",
        "Grand Theft Auto 6",
        "shorts",
    ]
    assert puts == [
        (final_path, "shorts/c1.mp4"),
        (thumb_path, "shorts/c1.jpg"),
    ]
    assert not source.parent.exists()
    assert "Rendered and uploaded 1 clip(s), 0 failed." in capsys.readouterr().out


def test_render_failure_marks_failed_and_keeps_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A render failure marks the clip failed and keeps its work directory."""
    source = tmp_path / "c1" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"fake")
    statuses: list[tuple[object, ...]] = []

    def fake_status(
        clip_id: str, status: str, error: str | None = None, **fields: object
    ) -> bool:
        """Record a status update."""
        statuses.append((clip_id, status, error, fields))
        return True

    monkeypatch.setattr(
        "clipmachine.cli.load_config", lambda directory=None: _render_config()
    )
    monkeypatch.setattr("clipmachine.cli.expire_stale", lambda hours: 0)
    monkeypatch.setattr("clipmachine.cli.recover_abandoned_renders", lambda: 0)
    monkeypatch.setattr(db, "get_new_clips", lambda limit: [_clip()])
    monkeypatch.setattr(db, "get_new_clips_by_ids", lambda ids: [_clip()])
    monkeypatch.setattr("clipmachine.cli.download_clip", lambda clip: source)
    monkeypatch.setattr(
        "clipmachine.cli.detect_layout",
        lambda path, override, refine_cam_edges=True, box_override=None: Layout(
            "no_cam", None, 0.0
        ),
    )
    monkeypatch.setattr(db, "set_status", fake_status)
    monkeypatch.setattr("clipmachine.cli.transcribe", lambda path: [])
    monkeypatch.setattr(
        "clipmachine.cli.render_final",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("render exploded")
        ),
    )

    assert main(["render"]) == 0

    assert ("c1", "failed", "render exploded", {}) in statuses
    assert source.parent.exists()
    assert "Rendered and uploaded 0 clip(s), 1 failed." in capsys.readouterr().out


def test_render_upload_failure_deletes_partial_uploads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed thumbnail upload deletes the already-uploaded video."""
    source = tmp_path / "c1" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"fake")
    video_url = "https://blob.example/shorts/c1.mp4"
    statuses: list[tuple[object, ...]] = []
    deleted: list[str] = []

    def fake_status(
        clip_id: str, status: str, error: str | None = None, **fields: object
    ) -> bool:
        """Record a status update."""
        statuses.append((clip_id, status, error, fields))
        return True

    def fake_put(path: Path, pathname: str) -> str:
        """Return the video URL, then fail on the thumbnail."""
        if pathname.endswith(".mp4"):
            return video_url
        raise RuntimeError("thumb upload failed")

    monkeypatch.setattr(
        "clipmachine.cli.load_config", lambda directory=None: _render_config()
    )
    monkeypatch.setattr("clipmachine.cli.expire_stale", lambda hours: 0)
    monkeypatch.setattr("clipmachine.cli.recover_abandoned_renders", lambda: 0)
    monkeypatch.setattr(db, "get_new_clips", lambda limit: [_clip()])
    monkeypatch.setattr(db, "get_new_clips_by_ids", lambda ids: [_clip()])
    monkeypatch.setattr("clipmachine.cli.download_clip", lambda clip: source)
    monkeypatch.setattr(
        "clipmachine.cli.detect_layout",
        lambda path, override, refine_cam_edges=True, box_override=None: Layout(
            "no_cam", None, 0.0
        ),
    )
    monkeypatch.setattr(db, "set_status", fake_status)
    monkeypatch.setattr("clipmachine.cli.transcribe", lambda path: [])
    monkeypatch.setattr(
        "clipmachine.cli.render_final", lambda *args, **kwargs: None
    )
    monkeypatch.setattr("clipmachine.cli.put_file", fake_put)
    monkeypatch.setattr(
        "clipmachine.cli.delete_url", lambda url: deleted.append(url)
    )
    monkeypatch.setattr(
        "clipmachine.cli.moderation.screen_clip",
        lambda video, thumb, settings: moderation.ClipScreening(
            moderation.CLEAN, 0.0
        ),
    )

    assert main(["render"]) == 0

    assert deleted == [video_url]
    assert ("c1", "failed", "thumb upload failed", {}) in statuses


def test_render_skips_captions_when_burned_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Burned-in captions skip transcription and our ASS file."""
    source = tmp_path / "c1" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"fake")
    recorded_words: list[object] = []

    def fake_status(
        clip_id: str, status: str, error: str | None = None, **fields: object
    ) -> bool:
        """Record a status update."""
        return True

    def fake_build_ass(words: object, layout: Layout, path: Path) -> None:
        """Record the words passed to the caption builder."""
        recorded_words.append(words)
        return None

    monkeypatch.setattr(
        "clipmachine.cli.load_config", lambda directory=None: _render_config()
    )
    monkeypatch.setattr("clipmachine.cli.expire_stale", lambda hours: 0)
    monkeypatch.setattr("clipmachine.cli.recover_abandoned_renders", lambda: 0)
    monkeypatch.setattr(db, "get_new_clips", lambda limit: [_clip()])
    monkeypatch.setattr(db, "get_new_clips_by_ids", lambda ids: [_clip()])
    monkeypatch.setattr("clipmachine.cli.download_clip", lambda clip: source)
    monkeypatch.setattr(
        "clipmachine.cli.detect_layout",
        lambda path, override, refine_cam_edges=True, box_override=None: Layout(
            "cam_top", (0, 184, 400, 258), 1.0, None, "box", 1.0, False
        ),
    )
    monkeypatch.setattr(db, "set_status", fake_status)
    monkeypatch.setattr("clipmachine.cli.has_burned_captions", lambda path: True)
    monkeypatch.setattr(
        "clipmachine.cli.transcribe",
        lambda path: (_ for _ in ()).throw(AssertionError("should not transcribe")),
    )
    monkeypatch.setattr("clipmachine.cli.build_ass", fake_build_ass)
    monkeypatch.setattr(
        "clipmachine.cli.render_final", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "clipmachine.cli.put_file", lambda path, pathname: f"https://blob/{pathname}"
    )
    monkeypatch.setattr("clipmachine.cli.delete_url", lambda url: None)
    monkeypatch.setattr(
        "clipmachine.cli.moderation.screen_clip",
        lambda video, thumb, settings: moderation.ClipScreening(
            moderation.CLEAN, 0.0
        ),
    )

    assert main(["render"]) == 0
    assert recorded_words == [[]]


def test_upload_dispatches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """upload calls run_upload and exits successfully."""
    called: list[bool] = []
    monkeypatch.setattr(
        "clipmachine.cli.run_upload", lambda: called.append(True)
    )

    assert main(["upload"]) == 0
    assert called == [True]
