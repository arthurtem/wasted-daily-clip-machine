"""Automated nudity screening for rendered clips.

Clips are sampled into still frames and scored with NudeNet. Anything explicit
is rejected before it can be approved, borderline frames only ever lower the
upload privacy to unlisted, and a clean frame is used for the thumbnail so the
preview image cannot be what gets the channel flagged.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clipmachine import render

logger = logging.getLogger(__name__)

CLEAN = "clean"
BORDERLINE = "borderline"
EXPLICIT = "explicit"

DEFAULT_FRAMES = 10
DEFAULT_EXPLICIT_THRESHOLD = 0.50
DEFAULT_REVIEW_THRESHOLD = 0.30

EXPOSED_LABELS = frozenset(
    {
        "FEMALE_BREAST_EXPOSED",
        "FEMALE_GENITALIA_EXPOSED",
        "MALE_GENITALIA_EXPOSED",
        "BUTTOCKS_EXPOSED",
        "ANUS_EXPOSED",
    }
)

RISKY_TERMS = (
    "18+",
    "anal",
    "bikini",
    "blowjob",
    "boob",
    "boobs",
    "booty",
    "brothel",
    "cock",
    "dick",
    "dildo",
    "fuck",
    "fucking",
    "gone wild",
    "handjob",
    "hardcore",
    "hentai",
    "horny",
    "lingerie",
    "milf",
    "naked",
    "nakedness",
    "nipple",
    "nipples",
    "nsfw",
    "nude",
    "nudes",
    "nudity",
    "onlyfans",
    "orgy",
    "peg",
    "pegging",
    "porn",
    "porno",
    "pussy",
    "sex",
    "sex scene",
    "sexual",
    "sexy",
    "shower scene",
    "strip club",
    "stripper",
    "thot",
    "tits",
    "twerk",
    "xxx",
)

_RISKY_TEXT = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(term) for term in RISKY_TERMS) + r")(?![a-z])",
    re.IGNORECASE,
)

_LEVEL_RANK = {CLEAN: 0, BORDERLINE: 1, EXPLICIT: 2}


class ModerationUnavailable(RuntimeError):
    """Raised when clips cannot be screened, so they must not be published."""


@dataclass(frozen=True)
class Verdict:
    """The screening result for a single image."""

    level: str
    score: float
    labels: tuple[str, ...] = ()

    @property
    def blocked(self) -> bool:
        """Return whether the image must never be published."""
        return self.level == EXPLICIT


@dataclass(frozen=True)
class VideoScreening:
    """The combined verdict for a video plus a frame that is safe to show."""

    level: str
    score: float
    labels: tuple[str, ...] = ()
    safe_timestamp: float | None = None

    @property
    def blocked(self) -> bool:
        """Return whether the video must never be published."""
        return self.level == EXPLICIT


@dataclass(frozen=True)
class ClipScreening:
    """The verdict for a rendered clip and its thumbnail."""

    level: str
    score: float
    labels: tuple[str, ...] = ()
    thumbnail_replaced: bool = False

    @property
    def blocked(self) -> bool:
        """Return whether the clip must be rejected instead of uploaded."""
        return self.level == EXPLICIT

    @property
    def unlisted(self) -> bool:
        """Return whether the clip should only be uploaded as unlisted."""
        return self.level == BORDERLINE


def risky_text(*values: object) -> str | None:
    """Return the first sexual term found in clip text, if any."""
    for value in values:
        if not value:
            continue
        match = _RISKY_TEXT.search(str(value))
        if match:
            return match.group(0).lower()
    return None


def verdict_from_detections(
    detections: Iterable[dict[str, Any]],
    *,
    explicit_threshold: float = DEFAULT_EXPLICIT_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> Verdict:
    """Turn NudeNet detections into a clean, borderline, or explicit verdict."""
    hits: list[tuple[str, float]] = []
    for detection in detections:
        label = str(detection.get("class") or "").strip().upper()
        score = float(detection.get("score") or 0.0)
        if label in EXPOSED_LABELS and score > 0:
            hits.append((label, score))
    if not hits:
        return Verdict(CLEAN, 0.0)
    labels = tuple(sorted({label for label, _ in hits}))
    top_score = max(score for _, score in hits)
    if top_score >= explicit_threshold:
        return Verdict(EXPLICIT, top_score, labels)
    if top_score >= review_threshold:
        return Verdict(BORDERLINE, top_score, labels)
    return Verdict(CLEAN, top_score, labels)


def sample_timestamps(duration: float, count: int) -> list[float]:
    """Return evenly spaced timestamps inside a clip duration."""
    if duration <= 0 or count <= 0:
        return []
    step = duration / count
    timestamps = [step * (index + 0.5) for index in range(count)]
    return [round(min(duration - 0.05, timestamp), 3) for timestamp in timestamps]


def probe_duration(path: Path) -> float:
    """Return a media file's duration in seconds, or 0 when unknown."""
    command = [
        render.ffprobe_bin(),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(
            "could not probe duration for %s: %s", path, result.stderr[-200:]
        )
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _extract_frame(source: Path, timestamp: float, out_path: Path) -> bool:
    """Write one frame at a timestamp; return whether it was produced."""
    command = [
        render.ffmpeg_bin(),
        "-y",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(
            "could not extract frame at %.2fs from %s: %s",
            timestamp,
            source,
            result.stderr[-200:],
        )
        return False
    return out_path.exists() and out_path.stat().st_size > 0


_detector: Any | None = None


def detector() -> Any:
    """Return a lazily created NudeNet detector shared by this process."""
    global _detector
    if _detector is None:
        try:
            from nudenet import NudeDetector
        except Exception as exc:
            raise ModerationUnavailable(
                "nudenet is not installed; refusing to publish unscreened clips"
            ) from exc
        _detector = NudeDetector()
    return _detector


def detect_image(path: Path) -> list[dict[str, Any]]:
    """Return raw NudeNet detections for one image."""
    try:
        return list(detector().detect(str(path)))
    except ModerationUnavailable:
        raise
    except Exception as exc:
        raise ModerationUnavailable(f"nudity detection failed: {exc}") from exc


def screen_image(
    path: Path,
    *,
    explicit_threshold: float = DEFAULT_EXPLICIT_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> Verdict:
    """Screen a single image."""
    return verdict_from_detections(
        detect_image(path),
        explicit_threshold=explicit_threshold,
        review_threshold=review_threshold,
    )


def screen_video(
    path: Path,
    *,
    frames: int = DEFAULT_FRAMES,
    explicit_threshold: float = DEFAULT_EXPLICIT_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> VideoScreening:
    """Screen sampled frames of a video and pick a clean thumbnail timestamp."""
    duration = probe_duration(path)
    if duration <= 0:
        raise ModerationUnavailable(f"could not read the duration of {path.name}")

    results: list[tuple[float, Verdict]] = []
    with tempfile.TemporaryDirectory(prefix="moderation-") as work_dir:
        for index, timestamp in enumerate(sample_timestamps(duration, frames)):
            frame_path = Path(work_dir) / f"frame_{index:03d}.jpg"
            if not _extract_frame(path, timestamp, frame_path):
                continue
            verdict = screen_image(
                frame_path,
                explicit_threshold=explicit_threshold,
                review_threshold=review_threshold,
            )
            results.append((timestamp, verdict))
    if not results:
        raise ModerationUnavailable(f"no frames could be sampled from {path.name}")

    _, worst = max(
        results,
        key=lambda item: (_LEVEL_RANK[item[1].level], item[1].score),
    )
    clean = [timestamp for timestamp, verdict in results if verdict.level == CLEAN]
    midpoint = duration / 2
    safe_timestamp = (
        min(clean, key=lambda value: abs(value - midpoint)) if clean else None
    )
    return VideoScreening(
        worst.level,
        worst.score,
        worst.labels,
        safe_timestamp=safe_timestamp,
    )


def screen_clip(
    video_path: Path,
    thumb_path: Path,
    settings: object,
) -> ClipScreening:
    """Screen a rendered clip, replacing its thumbnail when it is unsafe."""
    frames = int(getattr(settings, "moderation_frames", DEFAULT_FRAMES))
    explicit_threshold = float(
        getattr(
            settings, "moderation_explicit_threshold", DEFAULT_EXPLICIT_THRESHOLD
        )
    )
    review_threshold = float(
        getattr(settings, "moderation_review_threshold", DEFAULT_REVIEW_THRESHOLD)
    )

    screening = screen_video(
        video_path,
        frames=frames,
        explicit_threshold=explicit_threshold,
        review_threshold=review_threshold,
    )
    thumb = screen_image(
        thumb_path,
        explicit_threshold=explicit_threshold,
        review_threshold=review_threshold,
    )
    replaced = False
    if thumb.level != CLEAN and screening.safe_timestamp is not None:
        if _extract_frame(video_path, screening.safe_timestamp, thumb_path):
            thumb = screen_image(
                thumb_path,
                explicit_threshold=explicit_threshold,
                review_threshold=review_threshold,
            )
            replaced = thumb.level == CLEAN

    if screening.blocked:
        level, score, labels = screening.level, screening.score, screening.labels
    elif thumb.level != CLEAN:
        level, score, labels = BORDERLINE, thumb.score, thumb.labels
    else:
        level, score, labels = CLEAN, 0.0, ()

    logger.info(
        "clip %s moderation level=%s score=%.2f labels=%s thumbnail_replaced=%s",
        video_path.parent.name,
        level,
        score,
        ",".join(labels) or "none",
        replaced,
    )
    return ClipScreening(level, score, labels, thumbnail_replaced=replaced)
