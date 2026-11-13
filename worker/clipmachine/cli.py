"""Command line entry point for the clipmachine worker."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

import psycopg

from clipmachine import db
from clipmachine.blob import delete_url, put_file
from clipmachine.calibrate import CalibrateError, run_calibrate
from clipmachine.captions import build_ass, has_burned_captions, transcribe
from clipmachine.config import ConfigError, load_config
from clipmachine.download import DownloadError, download_clip
from clipmachine.facecam import detect_layout
from clipmachine.fetch import run_fetch
from clipmachine.metadata import build_youtube_metadata
from clipmachine.render import render_final
from clipmachine.twitch import TwitchError

logger = logging.getLogger(__name__)


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


def cmd_render(args: argparse.Namespace) -> int:
    """Render new clips, upload them to Blob, and store YouTube metadata."""
    config = load_config(args.config_dir)
    settings = config.settings
    clips = db.get_clips("new", settings.max_clips_per_run)
    streamers_by_login = {
        streamer.twitch_login.lower(): streamer
        for streamer in config.streamers
    }
    rendered = 0
    failed = 0
    for clip in clips:
        clip_id = str(clip.get("id") or "")
        login = str(clip.get("streamer_login") or "").lower()
        logger.info("clip %s render start", clip_id)
        source = download_clip(clip)
        if source is None:
            failed += 1
            continue

        uploaded: list[str] = []
        try:
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

            metadata = build_youtube_metadata(clip)
            video_url = put_file(
                final_path, f"shorts/{clip_id}.mp4"
            )
            uploaded.append(video_url)
            thumb_url = put_file(
                thumb_path, f"shorts/{clip_id}.jpg"
            )
            uploaded.append(thumb_url)

            db.set_status(
                clip_id,
                "rendered",
                blob_url=video_url,
                thumb_url=thumb_url,
                yt_title=metadata.title,
                yt_description=metadata.description,
                yt_tags=metadata.tags,
            )
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

        try:
            shutil.rmtree(source.parent)
        except OSError as exc:
            logger.warning(
                "clip %s could not remove work directory: %s", clip_id, exc
            )
        rendered += 1
        logger.info("clip %s render complete layout=%s", clip_id, layout.kind)

    print(f"Rendered and uploaded {rendered} clip(s), {failed} failed.")
    return 0


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
    """Placeholder for the YouTube upload phase."""
    print("upload is not implemented yet.", file=sys.stderr)
    return 2


def cmd_reddit(args: argparse.Namespace) -> int:
    """Placeholder for the Reddit phase."""
    print("reddit is not implemented yet.", file=sys.stderr)
    return 2


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
