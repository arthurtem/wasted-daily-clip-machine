"""Shared fixtures and sample YAML for the clipmachine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

STREAMERS_YAML = """\
streamers:
  - name: "Kai Cenat"
    twitch_login: "kaicenat"
    enabled: true
    facecam_override: null
  - name: "xQc"
    twitch_login: "xqc"
    enabled: true
    facecam_override: top-right
  - name: "StableRonaldo"
    twitch_login: "stableronaldo"
    enabled: false
    facecam_override: none
"""

SETTINGS_YAML = """\
game_name: "Grand Theft Auto VI"
lookback_hours: 24
min_views: 200
max_clips_per_run: 10
max_clip_seconds: 60
uploads_per_run: 2
"""


def write_config(
    directory: Path,
    streamers: str = STREAMERS_YAML,
    settings: str = SETTINGS_YAML,
) -> Path:
    """Write streamers.yaml and settings.yaml into a directory."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "streamers.yaml").write_text(streamers, encoding="utf-8")
    (directory / "settings.yaml").write_text(settings, encoding="utf-8")
    return directory


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a valid config directory with config env vars unset."""
    monkeypatch.delenv("GAME_NAME", raising=False)
    monkeypatch.delenv("CLIPMACHINE_CONFIG_DIR", raising=False)
    return write_config(tmp_path / "config")
