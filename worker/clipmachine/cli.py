"""Command line entry point for the clipmachine worker."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import psycopg

from clipmachine import automation, db, moderation
from clipmachine.blob import delete_url, put_file
from clipmachine.calibrate import CalibrateError, run_calibrate
from clipmachine.captions import build_ass, has_burned_captions, transcribe
from clipmachine.config import ConfigError, load_config
from clipmachine.download import DownloadError, download_clip
from clipmachine.facecam import detect_layout
from clipmachine.fetch import run_fetch
from clipmachine.maintenance import expire_stale, recover_abandoned_renders
from clipmachine.metadata import build_youtube_metadata
from clipmachine.reddit import run_reddit
from clipmachine.render import render_final
from clipmachine.twitch import TwitchClient, TwitchError
from clipmachine.upload import run_upload

logger = logging.getLogger(__name__)


@contextmanager
def _time_limit(seconds: int):
    """Raise TimeoutError when a clip exceeds its render budget."""
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def handler(signum, frame):
        raise TimeoutError("timed out")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _cleanup_work_dir(directory: Path) -> None:
    """Remove a finished clip's work directory, warning on failure."""
    try:
        shutil.rmtree(directory)
    except OSError as exc:
        logger.warning("could not remove work directory %s: %s", directory, exc)


def cmd_check_config(args: argparse.Namespace) -> int:
    """Print the loaded streamers and settings."""
    config = load_config(args.config_dir)
    print(f"Streamers ({len(config.streamers)}):")
    for streamer in config.streamers:
        enabled = "yes" if streamer.enabled else "no"
        override = streamer.facecam_override or "auto"
        box_override = (
            list(streamer.facecam_box) if streamer.facecam_box else "auto"
        )
        print(
            f"  - {streamer.name} ({streamer.twitch_login}) "
            f"enabled={enabled} facecam_override={override} "
            f"facecam_box={box_override}"
        )
    settings = config.settings
    print("Settings:")
    print(f"  game_name: {settings.game_name}")
    print(f"  lookback_hours: {settings.lookback_hours}")
    print(f"  min_views: {settings.min_views}")
    print(f"  max_clips_per_run: {settings.max_clips_per_run}")
    print(f"  max_clip_seconds: {settings.max_clip_seconds}")
    print(f"  uploads_per_run: {settings.uploads_per_run}")
    print(f"  refine_cam_edges: {settings.refine_cam_edges}")
    print(f"  skip_burned_captions: {settings.skip_burned_captions}")
    return 0


def cmd_init_db(args: argparse.Namespace) -> int:
    """Create or update the database schema."""
    db.init_db()
    print("Database schema is up to date.")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """Fetch new clips from Twitch into the database."""
    result = run_fetch(args.config_dir)
    print(
        f"Fetched {result.new_clips} new clip(s) from "
        f"{result.streamers_checked} streamer(s)."
    )
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    """Render new clips, upload them to Blob, and store YouTube metadata."""
    config = load_config(args.config_dir)
    settings = config.settings
    limits = automation.current_limits(settings)
    settings = replace(settings, max_render_per_run=limits.render_limit)
    expire_stale(settings.stale_after_hours)
    recover_abandoned_renders()
    requested_ids = [
        value.strip()
        for value in os.environ.get("CLIP_IDS", "").split(",")
        if value.strip()
    ]
    if requested_ids:
        clips = db.get_new_clips_by_ids(requested_ids)
    else:
        clips = db.get_new_clips(settings.max_render_per_run)
    clips = clips[: settings.max_render_per_run]
    streamers_by_login = {
        streamer.twitch_login.lower(): streamer
        for streamer in config.streamers
    }
    auto_render = os.environ.get("AUTO_RENDER", "").strip() == "1"
    rendered = 0
    failed = 0
    rejected = 0
    for clip in clips:
        clip_id = str(clip.get("id") or "")
        login = str(clip.get("streamer_login") or "").lower()
        logger.info("clip %s render start", clip_id)
        uploaded: list[str] = []
        try:
            with _time_limit(settings.render_clip_timeout_seconds):
                source = download_clip(clip)
                if source is None:
                    failed += 1
                    continue

                streamer = streamers_by_login.get(login)
                layout = detect_layout(
                    source,
                    streamer.facecam_override if streamer else None,
                    settings.refine_cam_edges,
                    streamer.facecam_box if streamer else None,
                )
                if layout.needs_review:
                    logger.warning(
                        "clip %s facecam needs review: source=%s face_ratio=%s",
                        clip_id,
                        layout.source,
                        layout.face_ratio,
                    )
                db.set_status(clip_id, "downloaded", layout=layout.as_dict())

                if settings.skip_burned_captions and has_burned_captions(source):
                    logger.info(
                        "clip %s burned-in captions detected; skipping our captions",
                        clip_id,
                    )
                    words = []
                else:
                    words = transcribe(source)
                ass_path = build_ass(
                    words, layout, source.parent / "captions.ass"
                )
                final_path = source.parent / "final.mp4"
                thumb_path = source.parent / "thumb.jpg"
                render_final(
                    source,
                    layout,
                    final_path,
                    thumb_path,
                    ass_path,
                )

                screening = moderation.ClipScreening(moderation.CLEAN, 0.0)
                if getattr(settings, "moderation_enabled", True):
                    screening = moderation.screen_clip(
                        final_path, thumb_path, settings
                    )
                moderation_fields = {
                    "moderation_level": screening.level,
                    "moderation_score": screening.score,
                    "moderation_labels": ", ".join(screening.labels),
                }
                if screening.blocked:
                    labels = ", ".join(screening.labels) or "explicit"
                    db.set_status(
                        clip_id,
                        "rejected",
                        error=f"moderation: {labels}",
                        **moderation_fields,
                    )
                    logger.warning(
                        "clip %s rejected by moderation labels=%s score=%.2f",
                        clip_id,
                        labels,
                        screening.score,
                    )
                    rejected += 1
                    _cleanup_work_dir(source.parent)
                    continue

                metadata = build_youtube_metadata(clip)
                risky = moderation.risky_text(
                    clip.get("clip_title"), metadata.title
                )
                if risky:
                    db.set_status(
                        clip_id,
                        "rejected",
                        error=f"moderation: title:{risky}",
                        moderation_level=moderation.EXPLICIT,
                        moderation_score=1.0,
                        moderation_labels=f"title:{risky}",
                    )
                    logger.warning(
                        "clip %s rejected for sexual title term %r",
                        clip_id,
                        risky,
                    )
                    rejected += 1
                    _cleanup_work_dir(source.parent)
                    continue

                video_url = put_file(final_path, f"shorts/{clip_id}.mp4")
                uploaded.append(video_url)
                thumb_url = put_file(
                    thumb_path, f"shorts/{clip_id}.jpg"
                )
                uploaded.append(thumb_url)

                fields: dict[str, object] = {
                    "blob_url": video_url,
                    "thumb_url": thumb_url,
                    "yt_title": metadata.title,
                    "yt_description": metadata.description,
                    "yt_tags": metadata.tags,
                    **moderation_fields,
                }
                current_privacy = str(clip.get("yt_privacy") or "public")
                if screening.unlisted and current_privacy == "public":
                    fields["yt_privacy"] = "unlisted"
                    logger.info(
                        "clip %s marked unlisted after borderline moderation",
                        clip_id,
                    )
                db.set_status(
                    clip_id,
                    "approved" if settings.auto_approve else "rendered",
                    **fields,
                )
                if auto_render:
                    try:
                        db.mark_auto_rendered(clip_id)
                    except Exception:
                        logger.exception(
                            "clip %s rendered but auto-render marker failed",
                            clip_id,
                        )
        except TimeoutError:
            logger.error("clip %s render timed out", clip_id)
            for url in uploaded:
                try:
                    delete_url(url)
                except Exception:
                    logger.warning(
                        "clip %s could not delete uploaded blob", clip_id
                    )
            try:
                db.set_status(clip_id, "failed", error="timed out")
            except Exception:
                logger.exception("clip %s failed to store timeout", clip_id)
            failed += 1
            continue
        except Exception as exc:
            logger.exception("clip %s render failed", clip_id)
            for url in uploaded:
                try:
                    delete_url(url)
                except Exception:
                    logger.warning(
                        "clip %s could not delete uploaded blob %s",
                        clip_id,
                        url,
                    )
            try:
                db.set_status(clip_id, "failed", error=str(exc))
            except Exception:
                logger.exception("clip %s failed to store failure", clip_id)
            failed += 1
            continue

        _cleanup_work_dir(source.parent)
        rendered += 1
        logger.info("clip %s render complete layout=%s", clip_id, layout.kind)

    summary = f"Rendered and uploaded {rendered} clip(s), {failed} failed."
    if rejected:
        summary += f" Rejected {rejected} clip(s) by moderation."
    print(summary)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """Render clips, serialized in GitHub Actions."""
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        with db.advisory_lock(783420) as acquired:
            if not acquired:
                logger.info("another render is already running; skipping")
                return 0
            return _cmd_render(args)
    return _cmd_render(args)

def cmd_calibrate(args: argparse.Namespace) -> int:
    """Write a gridded calibration frame for choosing a facecam box."""
    image, streamer = run_calibrate(
        args.streamer, args.clip_id, args.config_dir
    )
    print(f"Calibration frame: {image}")
    print(
        f"Set for {streamer.name} ({streamer.twitch_login}) in "
        "config/streamers.yaml:"
    )
    print("  facecam_box: [x, y, w, h]   # fractions 0-1 from the grid")
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    """Upload approved clips to YouTube in API mode."""
    run_upload()
    return 0


def cmd_upload_gate(args: argparse.Namespace) -> int:
    """Run the lightweight upload preflight and print the decision."""
    from clipmachine.upload_gate import run_gate

    eligible, reason = run_gate()
    print(f"eligible={'true' if eligible else 'false'} reason={reason}")
    return 0


def cmd_reddit(args: argparse.Namespace) -> int:
    """Enrich/import trending Twitch clips found on Reddit."""
    config = load_config(args.config_dir)
    client = TwitchClient()
    game_id = client.get_game_id(config.settings.game_name)
    enabled = [streamer for streamer in config.streamers if streamer.enabled]
    user_ids = client.get_user_ids([s.twitch_login for s in enabled])
    affected = run_reddit(
        config.settings,
        client,
        game_id=game_id,
        user_ids=user_ids,
    )
    print(f"Reddit affected {len(affected)} clip(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the clipmachine argument parser."""
    parser = argparse.ArgumentParser(
        prog="clipmachine", description="Wasted Daily clip machine worker"
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="directory containing streamers.yaml and settings.yaml",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_config = subparsers.add_parser(
        "check-config", help="print streamers and settings"
    )
    check_config.set_defaults(func=cmd_check_config)

    init_db = subparsers.add_parser("init-db", help="create or update the schema")
    init_db.set_defaults(func=cmd_init_db)

    fetch = subparsers.add_parser("fetch", help="fetch clips from Twitch")
    fetch.set_defaults(func=cmd_fetch)

    render = subparsers.add_parser("render", help="render downloaded clips")
    render.set_defaults(func=cmd_render)

    calibrate = subparsers.add_parser(
        "calibrate", help="make a facecam calibration frame"
    )
    calibrate.add_argument("streamer", help="Twitch login of the streamer")
    calibrate.add_argument(
        "--clip-id",
        default=None,
        help="use an already downloaded clip instead of fetching one",
    )
    calibrate.set_defaults(func=cmd_calibrate)

    upload = subparsers.add_parser("upload", help="upload approved clips")
    upload.set_defaults(func=cmd_upload)

    upload_gate = subparsers.add_parser(
        "upload-gate", help="check upload window/cap/gap without heavy installs"
    )
    upload_gate.set_defaults(func=cmd_upload_gate)

    reddit = subparsers.add_parser("reddit", help="collect Reddit drops")
    reddit.set_defaults(func=cmd_reddit)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to a command."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        ConfigError,
        db.DatabaseError,
        TwitchError,
        CalibrateError,
        DownloadError,
        psycopg.Error,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
