"""Tests for Reddit link extraction."""

from clipmachine.reddit import extract_clip_id


def test_extracts_clip_domain() -> None:
    assert extract_clip_id("https://clips.twitch.tv/FunnyClip-abc_123?x=1") == "FunnyClip-abc_123"


def test_extracts_channel_clip_url() -> None:
    assert extract_clip_id("https://www.twitch.tv/xqc/clip/FunnyClip-abc_123") == "FunnyClip-abc_123"


def test_ignores_other_urls() -> None:
    assert extract_clip_id("https://youtube.com/watch?v=abc") is None
