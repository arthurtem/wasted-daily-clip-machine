# Wasted Daily Clip Machine

Turns Twitch clips of big streamers playing GTA VI into 1080x1920 YouTube Shorts
for **Wasted Daily**.

## Layout

```
/worker              Python package "clipmachine" (video + API logic)
  /clipmachine       config, database, CLI, shared models
  /migrations        SQL migrations
  /tests             pytest suite (mocked, no network)
/dashboard           Next.js review dashboard
/config              streamers.yaml and settings.yaml
/.github/workflows   GitHub Actions workflows
```

## Requirements

- Python 3.11
- A Postgres database (Neon)
- `ffmpeg`/`ffprobe` with `libass`, `freetype`, and `fontconfig`
  (Homebrew core ffmpeg lacks these; `FFMPEG_BIN`/`FFPROBE_BIN` can point at
  another build such as `ffmpeg-alt`)
- Node.js 18+ and npm (Vercel Blob helper)
- Twitch API credentials and a Vercel Blob read/write token
- faster-whisper downloads the `small` model on first use
- `tesseract` for the burned-in caption check (`brew install tesseract`); without
  it, the worker keeps adding its own captions

## Setup

```bash
# from the repo root
python3.11 -m venv worker/.venv
source worker/.venv/bin/activate
pip install -e "worker[dev]"
(cd worker/scripts && npm install)

cp .env.example .env
# fill in .env, then load it into your shell, for example:
set -a && source .env && set +a
```

Configuration lives in `config/streamers.yaml` and `config/settings.yaml`.
`GAME_NAME` overrides `game_name` from `settings.yaml`. `CLIPMACHINE_CONFIG_DIR`
can point at a different config directory.

## Commands

```bash
python -m clipmachine check-config   # print streamers and settings
python -m clipmachine init-db        # apply migrations (safe to run again)
python -m clipmachine fetch          # fetch clips from Twitch into the database
python -m clipmachine render         # download, caption, render, upload, store metadata
python -m clipmachine calibrate kaicenat  # grid image to choose a facecam_box
python -m clipmachine upload         # placeholder (phase 5)
python -m clipmachine reddit         # placeholder (later)
```

`fetch` needs `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` in the environment.
Until GTA VI clips exist (19 November 2026), test with
`GAME_NAME="Grand Theft Auto V" python -m clipmachine fetch`.

## Work directory

`render` writes to `work/<clip_id>/` (gitignored): `source.mp4`, `detect.jpg`
(face boxes in yellow, detected cam box in green), `captions.ass`,
`final.mp4`, and `thumb.jpg`. The hook is used only for the YouTube title,
not drawn on the video. On success both files are uploaded to Blob as
`shorts/<clip_id>.mp4` and `shorts/<clip_id>.jpg`, the row becomes `rendered`,
and the work directory is deleted. Failures keep the work directory and mark
the clip `failed`; any partial uploads are deleted.
Set `CLIPMACHINE_WORK_DIR` or `--config-dir` to relocate things.
`refine_cam_edges` in `settings.yaml` controls the Canny/Hough border snap
(default `true`).

Per streamer, use either `facecam_override` (`top-left`, `top-right`,
`bottom-left`, `bottom-right`, `none`) or `facecam_box: [x, y, w, h]` with
fractions of the frame (for cams that are not flush in a corner). Setting both
is an error. A box skips face detection and crops exactly that region.

To onboard a streamer, run `calibrate <twitch_login>` (add `--clip-id ID` to
reuse a downloaded clip). It writes `calibrate.jpg` with a 100px grid and the
current box in green; read the box coordinates off it and set `facecam_box`.
Every render then face-detects inside the chosen box and stores `source`,
`face_ratio`, and `needs_review` in the layout JSON. A warning is logged when
the cam moved or no face is visible, so the reviewer knows to check that clip.

## Captions and uploads

`WHISPER_CACHE_DIR` is where faster-whisper stores its model (default
`.cache/whisper`). Captions are skipped silently when a clip has no speech.
With `skip_burned_captions: true` (default), the worker OCRs the bottom-center
band of sampled frames first; if existing burned-in captions are detected,
transcription and our ASS captions are skipped for that clip. HUD labels in
all caps are ignored to reduce false positives. Set it to `false` in
`settings.yaml` to always add our captions.
`BLOB_READ_WRITE_TOKEN` is read by `worker/scripts/blob.mjs`; keep
`worker/scripts/node_modules` installed. YouTube metadata is generated from the
clip title hook and stored on the row (`yt_title`, `yt_description`, `yt_tags`) for the
review dashboard.

`--config-dir PATH` must come before the command, e.g.
`python -m clipmachine --config-dir config check-config`.

## Tests

```bash
pytest worker/tests
```

The suite mocks every external call and needs no database. An optional
integration test runs only when `DATABASE_URL` is set; it calls `init_db()`
twice against that database and checks that the `clips` table and indexes exist.


## Dashboard

The review dashboard lives in `/dashboard` (Next.js App Router, TypeScript,
Tailwind). It only reads/writes Postgres and dispatches GitHub workflows.

```bash
cd dashboard
npm install
cp .env.example .env.local   # fill in the values
npm run dev                  # http://localhost:3000
npm run build                # production build / type check
```

Auth uses one `DASHBOARD_PASSWORD` and a signed httpOnly cookie
(`SESSION_SECRET`). `proxy.ts` redirects unauthenticated pages to `/login` and
returns 401 for API routes. `UPLOAD_MODE=manual` hides the upload button;
`UPLOAD_MODE=api` shows it once the YouTube API audit is approved.


### Manual posting (`/post`)

With `UPLOAD_MODE=manual`, approved clips appear at `/post`, oldest approval
first. Each card has the video, a same-origin **Download MP4** link
(`<streamer_login>-<clip_id>.mp4`), copy-title/copy-description buttons, and a
YouTube Shorts link field.

`POST /api/clips/[id]/posted` accepts `youtube.com/shorts/...`,
`youtu.be/...`, or `youtube.com/watch?v=...`, saves the video id, sets the clip
to `uploaded`, and deletes the video + thumbnail from Vercel Blob. The
dashboard therefore needs `BLOB_READ_WRITE_TOKEN` in every environment where
posting is used. The header shows a **Post** badge with the number of clips
waiting.

### Deploy to Vercel

1. Import the GitHub repo in Vercel and set **Root Directory** to `dashboard`.
   Framework preset: Next.js.
2. Add these environment variables (Production and Preview):
   `DATABASE_URL`, `DASHBOARD_PASSWORD`, `SESSION_SECRET`, `GITHUB_TOKEN`,
   `GITHUB_OWNER`, `GITHUB_REPO`, `UPLOAD_MODE`.
   Generate `SESSION_SECRET` with `openssl rand -base64 32`.
3. From the Vercel **Storage** tab, connect **Neon Postgres** and **Vercel
   Blob**. This injects `DATABASE_URL` and `BLOB_READ_WRITE_TOKEN`.
4. Create a fine-grained GitHub token with **Actions: read and write** on this
   repository only and use it as `GITHUB_TOKEN`.
5. Push to `main`; Vercel deploys automatically. The run buttons dispatch
   `.github/workflows/pipeline.yml` and `upload.yml`, so those files must exist
   on `main` before the buttons succeed.

## Database

`worker/migrations/001_init.sql` creates the `clips` table with statuses:

```
new -> downloaded -> rendered -> approved -> uploaded
rendered -> rejected
any -> failed
```

Indexes exist on `status` and `streamer_login`.
