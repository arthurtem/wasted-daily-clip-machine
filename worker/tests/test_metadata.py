"""Tests for YouTube metadata generation."""

from __future__ import annotations

from clipmachine.metadata import build_youtube_metadata

CLIP = {
    "clip_title": "Kai loses it completely after this play",
    "streamer_name": "Kai Cenat",
    "streamer_login": "kaicenat",
    "clip_url": "https://clips.twitch.tv/ClipAbc",
}


def test_metadata_fields() -> None:
    """Title, description, and tags follow the required format."""
    metadata = build_youtube_metadata(CLIP)

    assert metadata.title.endswith("| Kai Cenat GTA 6 #shorts")
    assert metadata.description == "\n".join(
        [
            "Kai Cenat live on Twitch: https://twitch.tv/kaicenat",
            "Original clip: https://clips.twitch.tv/ClipAbc",
            "#GTA6 #GTAVI #kaicenat #shorts",
        ]
    )
    assert metadata.tags == [
        "GTA 6",
        "GTA VI",
        "Kai Cenat",
        "Grand Theft Auto 6",
        "shorts",
    ]


def test_title_is_at_most_100_characters() -> None:
    """A long hook and name still produce a valid title length."""
    clip = dict(CLIP)
    clip["clip_title"] = " ".join(["absolutely incredible gameplay"] * 5)
    clip["streamer_name"] = "A" * 80

    metadata = build_youtube_metadata(clip)

    assert len(metadata.title) <= 100
