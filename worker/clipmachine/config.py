"""Load and validate the YAML configuration for the worker."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

FACECAM_OVERRIDES = frozenset(
    {"top-left", "top-right", "bottom-left", "bottom-right", "none"}
)
CONFIG_DIR_ENV = "CLIPMACHINE_CONFIG_DIR"
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class ConfigError(ValueError):
    """Raised when a configuration file is missing or invalid."""


@dataclass(frozen=True)
class Streamer:
    """One streamer entry from streamers.yaml."""

    name: str
    twitch_login: str
    enabled: bool = True
    facecam_override: str | None = None
    facecam_box: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class Settings:
    """Global worker settings from settings.yaml."""

    game_name: str
    lookback_hours: int
    min_views: int
    max_clips_per_run: int
    max_clip_seconds: int
    uploads_per_run: int
    refine_cam_edges: bool = True
    skip_burned_captions: bool = True


@dataclass(frozen=True)
class AppConfig:
    """The fully loaded and validated worker configuration."""

    streamers: tuple[Streamer, ...]
    settings: Settings


def config_dir(explicit: Path | None = None) -> Path:
    """Resolve the config directory from an argument, env var, or repo default."""
    if explicit is not None:
        return Path(explicit)
    env_value = os.environ.get(CONFIG_DIR_ENV, "").strip()
    if env_value:
        return Path(env_value)
    return DEFAULT_CONFIG_DIR


def _load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file and require a top-level mapping."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"missing config file: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a YAML mapping")
    return data


def _parse_facecam_box(
    value: Any, context: str
) -> tuple[float, float, float, float] | None:
    """Validate a fractional [x, y, w, h] facecam box override."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ConfigError(f"{context}: facecam_box must be [x, y, w, h] fractions")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ConfigError(f"{context}: facecam_box values must be numbers")
        number = float(item)
        if not (0.0 <= number <= 1.0):
            raise ConfigError(
                f"{context}: facecam_box values must be between 0 and 1"
            )
        numbers.append(number)
    x, y, width, height = numbers
    if width <= 0 or height <= 0 or x + width > 1.000001 or y + height > 1.000001:
        raise ConfigError(f"{context}: facecam_box must fit inside the frame")
    return (x, y, width, height)


def load_streamers(path: Path) -> tuple[Streamer, ...]:
    """Load and validate the streamers list from streamers.yaml."""
    data = _load_yaml(path)
    raw_streamers = data.get("streamers")
    if not isinstance(raw_streamers, list):
        raise ConfigError(f"{path}: 'streamers' must be a list")

    streamers: list[Streamer] = []
    seen_logins: set[str] = set()
    for index, raw in enumerate(raw_streamers):
        context = f"{path}: streamers[{index}]"
        if not isinstance(raw, dict):
            raise ConfigError(f"{context}: each streamer must be a mapping")

        login = raw.get("twitch_login")
        if not isinstance(login, str) or not login.strip():
            raise ConfigError(
                f"{context}: twitch_login is required and must be a non-empty string"
            )
        login = login.strip()
        context = f"{context} ({login})"

        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(
                f"{context}: name is required and must be a non-empty string"
            )

        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError(f"{context}: enabled must be true or false")

        override = raw.get("facecam_override")
        if override is not None and override not in FACECAM_OVERRIDES:
            allowed = ", ".join(sorted(FACECAM_OVERRIDES))
            raise ConfigError(
                f"{context}: facecam_override must be null or one of {allowed}; "
                f"got {override!r}"
            )

        box_override = _parse_facecam_box(raw.get("facecam_box"), context)
        if override is not None and box_override is not None:
            raise ConfigError(
                f"{context}: set either facecam_override or facecam_box, not both"
            )

        if login in seen_logins:
            raise ConfigError(f"{context}: duplicate twitch_login")
        seen_logins.add(login)

        streamers.append(
            Streamer(
                name=name.strip(),
                twitch_login=login,
                enabled=enabled,
                facecam_override=override,
                facecam_box=box_override,
            )
        )

    if not streamers:
        raise ConfigError(f"{path}: at least one streamer is required")
    return tuple(streamers)


def load_settings(
    path: Path, environ: Mapping[str, str] | None = None
) -> Settings:
    """Load and validate settings.yaml, honouring the GAME_NAME override."""
    env = os.environ if environ is None else environ
    data = _load_yaml(path)

    game_name = data.get("game_name")
    if not isinstance(game_name, str) or not game_name.strip():
        raise ConfigError(
            f"{path}: game_name is required and must be a non-empty string"
        )
    game_override = env.get("GAME_NAME", "").strip()
    if game_override:
        game_name = game_override

    ranges = {
        "lookback_hours": 1,
        "min_views": 0,
        "max_clips_per_run": 1,
        "max_clip_seconds": 1,
        "uploads_per_run": 0,
    }
    values: dict[str, int] = {}
    for key, minimum in ranges.items():
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{path}: {key} must be an integer")
        if value < minimum:
            raise ConfigError(f"{path}: {key} must be >= {minimum}; got {value}")
        values[key] = value

    refine_cam_edges = data.get("refine_cam_edges", True)
    if not isinstance(refine_cam_edges, bool):
        raise ConfigError(f"{path}: refine_cam_edges must be true or false")

    skip_burned_captions = data.get("skip_burned_captions", True)
    if not isinstance(skip_burned_captions, bool):
        raise ConfigError(
            f"{path}: skip_burned_captions must be true or false"
        )

    return Settings(
        game_name=game_name.strip(),
        refine_cam_edges=refine_cam_edges,
        skip_burned_captions=skip_burned_captions,
        **values,
    )


def load_config(
    directory: Path | None = None, environ: Mapping[str, str] | None = None
) -> AppConfig:
    """Load and validate streamers.yaml and settings.yaml."""
    resolved = config_dir(directory)
    streamers = load_streamers(resolved / "streamers.yaml")
    settings = load_settings(resolved / "settings.yaml", environ=environ)
    logger.info(
        "loaded config from %s: %d streamers, game=%s",
        resolved,
        len(streamers),
        settings.game_name,
    )
    return AppConfig(streamers=streamers, settings=settings)
