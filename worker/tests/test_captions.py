"""Tests for ASS caption building."""

from __future__ import annotations

from pathlib import Path

from clipmachine.captions import build_ass, build_ass_text, group_words
from clipmachine.facecam import Layout


def word(text: str, start: float, end: float) -> dict[str, object]:
    """Build one faster-whisper style word token."""
    return {"word": text, "start": start, "end": end}


def test_group_words_breaks_on_pause() -> None:
    """A pause longer than 0.4s starts a new line."""
    words = [
        word("one", 0.0, 0.3),
        word("two", 0.35, 0.6),
        word("three", 0.65, 0.9),
        word("four", 1.6, 1.8),
        word("five", 1.85, 2.0),
    ]

    lines = group_words(words)

    assert [[item["word"] for item in line] for line in lines] == [
        ["one", "two", "three"],
        ["four", "five"],
    ]


def test_group_words_limits_to_three() -> None:
    """Continuous speech is split every three words."""
    words = [word(f"w{index}", index * 0.2, index * 0.2 + 0.15) for index in range(4)]

    lines = group_words(words)

    assert [len(line) for line in lines] == [3, 1]


def test_ass_positions_cam_top_at_seam() -> None:
    """cam_top captions are centered on y=640."""
    text = build_ass_text(
        [word("hello", 0.0, 0.4), word("world", 0.5, 0.9)],
        Layout("cam_top", (0, 0, 10, 10), 1.0),
    )

    assert "\\pos(540,640)" in text
    assert "DejaVu Sans,78" in text
    assert "\\c&H00FFFF&" in text
    assert "Outline" in text


def test_ass_positions_other_layouts_at_1350() -> None:
    """no_cam and full_face captions sit at y=1350."""
    words = [word("hello", 0.0, 0.4), word("world", 0.5, 0.9)]

    for kind in ("no_cam", "full_face"):
        text = build_ass_text(words, Layout(kind, None, 1.0))
        assert "\\pos(540,1350)" in text


def test_build_ass_skips_empty_transcript(tmp_path: Path) -> None:
    """No words means no ASS file and no failure."""
    target = tmp_path / "captions.ass"

    assert build_ass([], Layout("no_cam", None, 1.0), target) is None
    assert not target.exists()


def test_build_ass_writes_file(tmp_path: Path) -> None:
    """A transcript produces a real .ass file."""
    target = tmp_path / "captions.ass"

    path = build_ass(
        [word("hello", 0.0, 0.4)], Layout("cam_top", (0, 0, 10, 10), 1.0), target
    )

    assert path == target
    assert target.read_text(encoding="utf-8").startswith("[Script Info]")


def test_caption_decision_needs_multiple_frames() -> None:
    """A single text-bearing frame is not enough to skip captions."""
    from clipmachine.captions import _looks_like_captions

    assert _looks_like_captions([0, 3, 0, 0, 0]) is False
    assert _looks_like_captions([0, 3, 0, 2, 0]) is True


def test_ocr_ignores_all_caps_hud_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HUD labels like STOP ENGINE are not treated as captions."""
    import numpy as np
    import pytesseract

    from clipmachine.captions import _count_ocr_words

    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *args, **kwargs: {
            "text": ["STOP", "ENGINE", "nothing", "buddy", "A"],
            "conf": [95, 95, 95, 95, 95],
        },
    )

    assert _count_ocr_words(np.zeros((10, 10), dtype=np.uint8)) == 2


def test_has_burned_captions_without_tesseract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing tesseract degrades to keeping our captions."""
    from clipmachine import captions

    monkeypatch.setattr(captions.shutil, "which", lambda name: None)

    assert captions.has_burned_captions(tmp_path / "source.mp4") is False
