"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from clipmachine.config import (
    ConfigError,
    load_config,
    load_settings,
    load_streamers,
)
from conftest import SETTINGS_YAML, STREAMERS_YAML, write_config


def test_load_config_returns_three_streamers(config_dir: Path) -> None:
    """A valid config directory loads all streamers and settings."""
    config = load_config(config_dir)

    assert [streamer.twitch_login for streamer in config.streamers] == [
        "kaicenat",
        "xqc",
        "stableronaldo",
    ]
    assert config.streamers[1].facecam_override == "top-right"
    assert config.streamers[2].enabled is False
    assert config.settings.game_name == "Grand Theft Auto VI"
    assert config.settings.lookback_hours == 24
    assert config.settings.uploads_per_run == 2


def test_repo_config_has_three_enabled_streamers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The checked-in repo config contains the three example streamers."""
    monkeypatch.delenv("GAME_NAME", raising=False)
    monkeypatch.delenv("CLIPMACHINE_CONFIG_DIR", raising=False)

    config = load_config()

    assert len(config.streamers) == 3
    assert all(streamer.enabled for streamer in config.streamers)
    assert {streamer.twitch_login for streamer in config.streamers} == {
        "kaicenat",
        "xqc",
        "stableronaldo",
    }


def test_game_name_env_override(config_dir: Path) -> None:
    """GAME_NAME overrides game_name from settings.yaml."""
    settings = load_settings(
        config_dir / "settings.yaml", environ={"GAME_NAME": "GTA VI Test"}
    )

    assert settings.game_name == "GTA VI Test"


def test_invalid_facecam_override_has_clear_error(tmp_path: Path) -> None:
    """An unsupported facecam_override is rejected with a helpful message."""
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

    with pytest.raises(ConfigError) as exc_info:
        load_config(directory)

    message = str(exc_info.value)
    assert "facecam_override" in message
    assert "middle" in message
    assert "top-left" in message


def test_missing_twitch_login_has_clear_error(tmp_path: Path) -> None:
    """A streamer without twitch_login is rejected."""
    path = tmp_path / "streamers.yaml"
    path.write_text(
        """\
streamers:
  - name: "xQc"
    enabled: true
    facecam_override: null
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as exc_info:
        load_streamers(path)

    message = str(exc_info.value)
    assert "streamers[0]" in message
    assert "twitch_login" in message


def test_duplicate_login_is_rejected(tmp_path: Path) -> None:
    """Two streamers cannot share a Twitch login."""
    path = tmp_path / "streamers.yaml"
    path.write_text(
        STREAMERS_YAML + """\
  - name: "Kai Again"
    twitch_login: "kaicenat"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="duplicate twitch_login"):
        load_streamers(path)


def test_invalid_setting_is_rejected(tmp_path: Path) -> None:
    """Numeric settings must be positive where required."""
    directory = write_config(
        tmp_path / "bad-settings",
        settings=SETTINGS_YAML.replace("lookback_hours: 24", "lookback_hours: 0"),
    )

    with pytest.raises(ConfigError, match="lookback_hours must be >= 1"):
        load_config(directory)


def test_missing_config_file_is_rejected(tmp_path: Path) -> None:
    """A missing config directory produces a clear error."""
    with pytest.raises(ConfigError, match="missing config file"):
        load_config(tmp_path / "does-not-exist")


def test_refine_cam_edges_defaults_true(config_dir: Path) -> None:
    """Older settings files get edge refinement enabled by default."""
    assert load_config(config_dir).settings.refine_cam_edges is True


def test_invalid_refine_cam_edges_is_rejected(tmp_path: Path) -> None:
    """refine_cam_edges must be a boolean."""
    directory = write_config(
        tmp_path / "bad-refine",
        settings=SETTINGS_YAML + 'refine_cam_edges: "yes"\n',
    )

    with pytest.raises(ConfigError, match="refine_cam_edges must be true or false"):
        load_config(directory)


def test_facecam_box_is_parsed(tmp_path: Path) -> None:
    """A fractional facecam box is validated and stored."""
    path = tmp_path / "streamers.yaml"
    path.write_text(
        """\
streamers:
  - name: "xQc"
    twitch_login: "xqc"
    facecam_box: [0.0, 0.2, 0.22, 0.3]
""",
        encoding="utf-8",
    )

    streamers = load_streamers(path)

    assert streamers[0].facecam_box == (0.0, 0.2, 0.22, 0.3)


def test_facecam_box_must_fit_inside_frame(tmp_path: Path) -> None:
    """A box that extends past the frame is rejected."""
    path = tmp_path / "streamers.yaml"
    path.write_text(
        """\
streamers:
  - name: "xQc"
    twitch_login: "xqc"
    facecam_box: [0.9, 0.2, 0.22, 0.3]
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="facecam_box must fit inside the frame"):
        load_streamers(path)


def test_facecam_box_and_override_conflict(tmp_path: Path) -> None:
    """Setting both override forms is ambiguous and rejected."""
    path = tmp_path / "streamers.yaml"
    path.write_text(
        """\
streamers:
  - name: "xQc"
    twitch_login: "xqc"
    facecam_override: "top-left"
    facecam_box: [0.0, 0.2, 0.22, 0.3]
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="not both"):
        load_streamers(path)


def test_skip_burned_captions_defaults_true(config_dir: Path) -> None:
    """Older settings files enable burned-caption skipping by default."""
    assert load_config(config_dir).settings.skip_burned_captions is True


def test_invalid_skip_burned_captions_is_rejected(tmp_path: Path) -> None:
    """skip_burned_captions must be a boolean."""
    directory = write_config(
        tmp_path / "bad-skip",
        settings=SETTINGS_YAML + 'skip_burned_captions: "sometimes"\n',
    )

    with pytest.raises(
        ConfigError, match="skip_burned_captions must be true or false"
    ):
        load_config(directory)


def test_moderation_defaults(config_dir: Path) -> None:
    """Moderation settings default to on with the documented thresholds."""
    settings = load_settings(config_dir / "settings.yaml")

    assert settings.moderation_enabled is True
    assert settings.moderation_frames == 60
    assert settings.moderation_explicit_threshold == pytest.approx(0.35)
    assert settings.moderation_review_threshold == pytest.approx(0.25)
    assert settings.moderation_pause_hours == 168


def test_out_of_range_moderation_threshold_is_rejected(tmp_path: Path) -> None:
    """A threshold above 1.0 is a configuration error."""
    directory = write_config(
        tmp_path / "bad",
        settings=SETTINGS_YAML + "moderation_explicit_threshold: 1.5\n",
    )

    with pytest.raises(ConfigError) as exc_info:
        load_settings(directory / "settings.yaml")

    assert "moderation_explicit_threshold" in str(exc_info.value)
