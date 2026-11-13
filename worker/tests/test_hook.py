"""Tests for hook cleaning and truncation."""

from __future__ import annotations

from clipmachine.hook import make_hook


def test_hook_cleans_emojis_urls_and_punctuation() -> None:
    """The acceptance example becomes a clean three-word hook."""
    clip = {
        "clip_title": "😭😭KAI LOST IT!!! https://x.co",
        "streamer_name": "Kai Cenat",
    }

    assert make_hook(clip) == "KAI LOST IT!"


def test_hook_falls_back_to_streamer_and_game() -> None:
    """Short or empty titles use the streamer fallback."""
    assert make_hook({"clip_title": "lol", "streamer_name": "xQc"}) == (
        "xQc in GTA 6"
    )
    assert make_hook({"clip_title": None, "streamer_name": "xQc"}) == (
        "xQc in GTA 6"
    )


def test_hook_removes_mentions() -> None:
    """@mentions are stripped from titles."""
    hook = make_hook(
        {"clip_title": "shoutout @friend for the clip", "streamer_name": "xQc"}
    )

    assert "@" not in hook
    assert hook == "shoutout for the clip"


def test_hook_truncates_at_word_boundary() -> None:
    """Long titles are cut to 40 characters without a partial word."""
    clip = {
        "clip_title": "one two three four five six seven eight nine ten",
        "streamer_name": "xQc",
    }

    hook = make_hook(clip)

    assert len(hook) <= 40
    assert not hook.endswith(" ")
    assert hook.split()[-1] in clip["clip_title"].split()
