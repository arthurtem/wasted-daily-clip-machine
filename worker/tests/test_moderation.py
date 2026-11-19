"""Tests for the automated nudity screening."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from clipmachine import moderation


def settings() -> SimpleNamespace:
    """Return the settings shape used by screen_clip."""
    return SimpleNamespace(
        moderation_frames=4,
        moderation_explicit_threshold=0.5,
        moderation_review_threshold=0.3,
    )


def test_verdict_ignores_non_sensitive_labels() -> None:
    """Exposed feet and faces are not nudity."""
    verdict = moderation.verdict_from_detections(
        [
            {"class": "FEET_EXPOSED", "score": 0.9},
            {"class": "FACE_MALE", "score": 0.8},
        ]
    )

    assert verdict.level == moderation.CLEAN
    assert verdict.labels == ()


def test_verdict_explicit_above_threshold() -> None:
    """A confident exposed label is explicit."""
    verdict = moderation.verdict_from_detections(
        [{"class": "FEMALE_BREAST_EXPOSED", "score": 0.72}],
        explicit_threshold=0.5,
        review_threshold=0.3,
    )

    assert verdict.level == moderation.EXPLICIT
    assert verdict.blocked is True
    assert verdict.labels == ("FEMALE_BREAST_EXPOSED",)


def test_verdict_borderline_between_thresholds() -> None:
    """Low-confidence exposure is only borderline."""
    verdict = moderation.verdict_from_detections(
        [{"class": "BUTTOCKS_EXPOSED", "score": 0.4}],
        explicit_threshold=0.5,
        review_threshold=0.3,
    )

    assert verdict.level == moderation.BORDERLINE
    assert verdict.blocked is False


def test_verdict_below_review_is_clean() -> None:
    """Scores under the review threshold are treated as clean."""
    verdict = moderation.verdict_from_detections(
        [{"class": "ANUS_EXPOSED", "score": 0.2}],
        explicit_threshold=0.5,
        review_threshold=0.3,
    )

    assert verdict.level == moderation.CLEAN
    assert verdict.score == pytest.approx(0.2)


def test_verdict_uses_highest_score() -> None:
    """The worst detection decides the verdict."""
    verdict = moderation.verdict_from_detections(
        [
            {"class": "FEMALE_BREAST_EXPOSED", "score": 0.4},
            {"class": "FEMALE_GENITALIA_EXPOSED", "score": 0.8},
        ],
        explicit_threshold=0.5,
        review_threshold=0.3,
    )

    assert verdict.level == moderation.EXPLICIT
    assert verdict.score == pytest.approx(0.8)
    assert verdict.labels == (
        "FEMALE_BREAST_EXPOSED",
        "FEMALE_GENITALIA_EXPOSED",
    )


def test_sample_timestamps_stay_inside_duration() -> None:
    """Timestamps are evenly spread and never past the clip end."""
    timestamps = moderation.sample_timestamps(10.0, 4)

    assert len(timestamps) == 4
    assert timestamps == sorted(timestamps)
    assert all(0 < timestamp < 10.0 for timestamp in timestamps)


def test_sample_timestamps_handles_unknown_duration() -> None:
    """A zero duration yields no frames."""
    assert moderation.sample_timestamps(0.0, 10) == []


def test_screen_video_flags_explicit_and_keeps_a_clean_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit sampled frame makes the clip explicit but keeps a safe time."""
    monkeypatch.setattr(moderation, "probe_duration", lambda path: 10.0)
    monkeypatch.setattr(
        moderation,
        "_extract_frame",
        lambda source, timestamp, out_path: True,
    )

    def fake_detect(path: Path) -> list[dict[str, object]]:
        """Flag only the second sampled frame."""
        index = int(path.stem.split("_")[1])
        if index == 1:
            return [{"class": "FEMALE_BREAST_EXPOSED", "score": 0.9}]
        return []

    monkeypatch.setattr(moderation, "detect_image", fake_detect)

    result = moderation.screen_video(
        Path("clip.mp4"),
        frames=4,
        explicit_threshold=0.5,
        review_threshold=0.3,
    )

    assert result.level == moderation.EXPLICIT
    assert result.labels == ("FEMALE_BREAST_EXPOSED",)
    assert result.safe_timestamp == pytest.approx(6.25)


def test_screen_video_requires_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clip that cannot be sampled is refused instead of published."""
    monkeypatch.setattr(moderation, "probe_duration", lambda path: 10.0)
    monkeypatch.setattr(
        moderation, "_extract_frame", lambda source, timestamp, out: False
    )

    with pytest.raises(moderation.ModerationUnavailable):
        moderation.screen_video(Path("clip.mp4"), frames=4)


def test_screen_clip_replaces_dirty_thumbnail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dirty thumbnail is replaced with a clean frame from the video."""
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    thumb = tmp_path / "thumb.jpg"
    thumb.write_text("dirty")

    monkeypatch.setattr(
        moderation,
        "screen_video",
        lambda path, **kwargs: moderation.VideoScreening(
            moderation.CLEAN, 0.0, safe_timestamp=4.0
        ),
    )

    def fake_screen_image(path: Path, **kwargs: object) -> moderation.Verdict:
        """Treat anything still marked dirty as explicit."""
        if path.read_text() == "dirty":
            return moderation.Verdict(
                moderation.EXPLICIT, 0.8, ("BUTTOCKS_EXPOSED",)
            )
        return moderation.Verdict(moderation.CLEAN, 0.0)

    monkeypatch.setattr(moderation, "screen_image", fake_screen_image)

    def fake_extract(source: Path, timestamp: float, out_path: Path) -> bool:
        """Write a clean replacement frame."""
        out_path.write_text("clean")
        return True

    monkeypatch.setattr(moderation, "_extract_frame", fake_extract)

    result = moderation.screen_clip(video, thumb, settings())

    assert result.level == moderation.CLEAN
    assert result.thumbnail_replaced is True
    assert thumb.read_text() == "clean"


def test_screen_clip_borderline_when_thumbnail_cannot_be_replaced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unreplaceable dirty thumbnail only downgrades the clip to unlisted."""
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    thumb = tmp_path / "thumb.jpg"
    thumb.write_text("dirty")

    monkeypatch.setattr(
        moderation,
        "screen_video",
        lambda path, **kwargs: moderation.VideoScreening(
            moderation.CLEAN, 0.0, safe_timestamp=None
        ),
    )
    monkeypatch.setattr(
        moderation,
        "screen_image",
        lambda path, **kwargs: moderation.Verdict(
            moderation.BORDERLINE, 0.4, ("FEMALE_BREAST_EXPOSED",)
        ),
    )

    result = moderation.screen_clip(video, thumb, settings())

    assert result.level == moderation.BORDERLINE
    assert result.unlisted is True
    assert result.blocked is False


def test_risky_text_matches_sexual_terms() -> None:
    """Sexual wording in clip titles is caught before upload."""
    assert moderation.risky_text("pegging in gta 6 gone wild") == "pegging"
    assert (
        moderation.risky_text("18+ GTA 6 First Nude Showering Scene") == "18+"
    )
    assert (
        moderation.risky_text("ohnePixel tries out the strip club's")
        == "strip club"
    )
    assert moderation.risky_text("i see dick hype") == "dick"


def test_risky_text_ignores_benign_titles() -> None:
    """Ordinary streamer titles are not blocked."""
    assert moderation.risky_text("IShowSpeed in GTA 6") is None
    assert moderation.risky_text("cars have security systems?") is None
    assert moderation.risky_text(None, "") is None
