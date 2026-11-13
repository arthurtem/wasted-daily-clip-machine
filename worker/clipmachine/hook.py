"""Build short hooks for YouTube titles."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MAX_HOOK_CHARS = 40
MIN_HOOK_WORDS = 3
FALLBACK_SUFFIX = "in GTA 6"

EMOJI_RE = re.compile(
    "[\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U0001F000-\U0001F0FF"
    "\uFE0F\u200D\u20E3]+"
)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"@\w+")
REPEATED_PUNCT_RE = re.compile(r"([!?.,])\1+")
WHITESPACE_RE = re.compile(r"\s+")


def _clean_title(title: str) -> str:
    """Strip emojis, links, mentions, and repeated punctuation from a title."""
    text = URL_RE.sub(" ", title)
    text = MENTION_RE.sub(" ", text)
    text = EMOJI_RE.sub(" ", text)
    text = REPEATED_PUNCT_RE.sub(r"\1", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def _truncate(text: str, limit: int) -> str:
    """Cut text to a limit at a word boundary."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = cut.rfind(" ")
    if boundary > 0:
        cut = cut[:boundary]
    return cut.rstrip(" ,.;:-")


def make_hook(clip: Mapping[str, Any]) -> str:
    """Return a short YouTube title hook derived from the clip title."""
    title = clip.get("clip_title")
    cleaned = _clean_title(title if isinstance(title, str) else "")
    hook = _truncate(cleaned, MAX_HOOK_CHARS)
    if not hook or len(hook.split()) < MIN_HOOK_WORDS:
        streamer = str(clip.get("streamer_name") or "Streamer").strip()
        hook = f"{streamer} {FALLBACK_SUFFIX}"
    return hook
