"""Tests for branded thumbnail composition."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from clipmachine import thumbnail


def test_compose_produces_9_by_16_jpeg(tmp_path: Path) -> None:
    """A source frame becomes a 1080x1920 JPEG."""
    source = tmp_path / "source.jpg"
    Image.new("RGB", (720, 1280), (20, 30, 40)).save(source, format="JPEG")
    output = tmp_path / "thumb.jpg"

    thumbnail.compose(source, output, "xQc loses it after this GTA 6 moment")

    assert output.exists()
    with Image.open(output) as image:
        assert image.size == thumbnail.SIZE
        assert image.format == "JPEG"
    assert output.stat().st_size < 2 * 1024 * 1024


def test_compose_handles_long_hooks(tmp_path: Path) -> None:
    """A very long hook still produces a valid thumbnail."""
    source = tmp_path / "source.jpg"
    Image.new("RGB", (400, 800), (90, 20, 20)).save(source, format="JPEG")
    output = tmp_path / "thumb.jpg"

    thumbnail.compose(source, output, "word " * 80)

    with Image.open(output) as image:
        assert image.size == thumbnail.SIZE


def test_compose_accepts_empty_hook(tmp_path: Path) -> None:
    """An empty hook renders the brand only."""
    source = tmp_path / "source.jpg"
    Image.new("RGB", (1080, 1920), (10, 10, 10)).save(source, format="JPEG")
    output = tmp_path / "thumb.jpg"

    thumbnail.compose(source, output, "")

    assert output.exists()
