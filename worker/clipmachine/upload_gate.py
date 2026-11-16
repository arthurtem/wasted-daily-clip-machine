"""Lightweight upload preflight: expiry, window, cap, gap, and queue check."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clipmachine import db
from clipmachine.config import load_config
from clipmachine.maintenance import expire_stale
from clipmachine.upload_policy import inside_window, policy_from_settings

logger = logging.getLogger(__name__)


def run_gate() -> tuple[bool, str]:
    """Return whether an upload job should run, plus a reason."""
    config = load_config()
    settings = config.settings
    expire_stale(settings.stale_after_hours)

    mode = os.environ.get("UPLOAD_MODE", "manual").strip().lower()
    if mode != "api":
        return False, "manual mode"

    policy = policy_from_settings(settings)
    now = datetime.now(timezone.utc)
    if not inside_window(now, policy):
        return False, "outside upload window"

    uploaded = db.count_uploads_since(now - timedelta(hours=24))
    if uploaded >= policy.max_uploads_per_day:
        return False, f"daily cap reached ({uploaded}/{policy.max_uploads_per_day})"

    latest = db.latest_upload_at()
    if latest is not None and now - latest < timedelta(
        minutes=policy.min_minutes_between_uploads
    ):
        return False, "minimum upload gap not met"

    if db.get_youtube_connection() is None:
        return False, "YouTube not connected"

    clips = db.get_approved_for_upload(
        1, settings.reddit_priority_hours
    )
    if not clips:
        return False, "no approved clips"

    return True, "eligible"


def main() -> int:
    """Run the gate and write a GitHub Actions output when available."""
    logging.basicConfig(level=logging.INFO)
    eligible, reason = run_gate()
    print(f"eligible={'true' if eligible else 'false'} reason={reason}")
    output = os.environ.get("GITHUB_OUTPUT", "").strip()
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"eligible={'true' if eligible else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
