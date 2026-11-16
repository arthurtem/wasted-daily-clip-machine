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
- Optional Reddit app credentials for trending discovery
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
python -m clipmachine fetch          # import clips + Reddit metadata + auto-render ids
python -m clipmachine render         # render selected/new clips (CLIP_IDS optional)
python -m clipmachine calibrate kaicenat  # grid image to choose a facecam_box
python -m clipmachine upload         # upload one approved clip (UPLOAD_MODE=api)
python -m clipmachine reddit         # enrich/import clips from Reddit trending
python -m clipmachine upload-gate    # lightweight upload preflight
```

`fetch` needs `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` in the environment.
Reddit enrichment additionally needs `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`,
and `REDDIT_USER_AGENT`; it only resolves Reddit posts to original Twitch clips.
Until GTA VI clips exist, test with Grand Theft Auto V and min views `0`.

Twitch category names verified for launch:
- `Grand Theft Auto VI` -> `1867279146`
- `Grand Theft Auto V` -> `32982`

Switching game/min views is configuration/environment only; no code change.

The fetch panel has two scopes:
- **Category top clips** (default): all clips in the game category over the last
  24 hours via Helix `game_id`, sorted by Twitch views. This matches Twitch's
  category clips page without scraping it.
- **Selected streamers**: the original per-streamer fetch.

Category mode defaults to `clip_language: en`. Global GTA V clips are currently
dominated by Japanese GTA RP, so English keeps the channel/audio audience
consistent. Set `clip_language: all` to ingest every language.


## Import inbox, auto-render, and freshness

`fetch` only imports clips. Imported clips are `new` and appear on `/inbox`
with their Twitch thumbnail, views, creation time, and optional Reddit score.
Nothing is downloaded or rendered until you click **Render selected**,
**Render all new**, or an auto-render rule matches.

Auto-render per fetch run:
- Any newly imported/enriched clip with a Reddit score.
- The top `auto_render_top_n` newly imported clips by Twitch views.
- Deduplicated and capped by `auto_render_max_per_run` and the rolling
  `auto_render_max_per_day` limit.

`render` accepts `CLIP_IDS` (comma-separated) and caps each run at
`max_render_per_run`. It marks `downloaded` only after the download completes
and `rendered` only after Blob uploads finish. A per-clip timeout marks the row
`failed` with `timed out`; abandoned downloads are recovered at the next render
run.

Approved or rendered clips older than `stale_after_hours` are rejected with
error `stale` and their Blob files are deleted at the start of upload/render.

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

For streamers not in `streamers.yaml`, auto-detection scans the full frame plus
four overlapping corner/quadrant crops, uses both MediaPipe face models, and
prefers a small persistent face near an edge. That is what separates an
unknown streamer's facecam from gameplay; centered in-game faces alone are
treated as `no_cam`.

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


### Public pages and compliance

`/` is a public landing page; logged-in users are redirected to `/queue`.
`/privacy` and `/terms` are public. `proxy.ts` protects `/queue`, `/post`,
`/history`, `/settings`, and all `/api/*` routes. Every page has a footer with
the privacy/terms links and the YouTube API Services notice.

Upload screens show a visibility selector (`public` / `unlisted` / `private`,
stored in `clips.yt_privacy`), the `CHANNEL_NAME` destination, and the YouTube
ToS/Community Guidelines acknowledgement above Approve. `/settings` connects
and shows the YouTube channel stored in `youtube_connection`.

Run the migrations after deploying schema changes:

```bash
python -m clipmachine init-db
```

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


For the Google API compliance review, the production deployment must be
public (turn off Vercel Deployment Protection / password protection) so the
`/`, `/privacy`, and `/terms` pages load without logging in. Use those two
legal URLs in the OAuth consent screen.

### Connect YouTube

`/settings` has a **Connect YouTube channel** button, owner-only. Add
`${APP_URL}/api/youtube/callback` as an authorized redirect URI in the Google
Cloud OAuth client and keep `APP_URL` free of a trailing slash. The connection
stores the refresh token encrypted with `TOKEN_ENCRYPTION_KEY` (AES-256-GCM),
which must be identical in Vercel and the worker environment.

`UPLOAD_MODE=api` uses the stored connection: `python -m clipmachine upload`
refreshes the token, uploads approved clips using each clip's `yt_privacy`
(falling back to `YT_PRIVACY_STATUS`), sets `uploaded`, and deletes the Blobs.
If YouTube is not connected it exits without changing clips; an invalid_grant
deletes the connection and leaves clips approved.


### Reviewer access

For app/API reviews (for example Google), set a separate `REVIEWER_PASSWORD`.
Logging in with it creates an **auditor** session: the dashboard pages render,
but approval, posting, workflow dispatch, and disconnect are disabled and the
write APIs return 403. The header shows “Review-only access”. Remove the
variable (or rotate it) after the review.


### Fetch and render workflows

The dashboard fetch panel searches Twitch (`/api/twitch/streamers`,
`/api/twitch/games`) and dispatches `fetch.yml`. It needs `TWITCH_CLIENT_ID`
and `TWITCH_CLIENT_SECRET` in the dashboard environment, plus the optional
Reddit secrets for enrichment. The configured streamers are selected initially;
search results outside `config/streamers.yaml` are resolved by Twitch.

`fetch.yml` runs every 30 minutes but enforces `fetch_interval_minutes` (90 by
default) for scheduled runs. Manual runs set `FORCE_FETCH=1`. Auto-render work
is dispatched as a separate `render.yml` run, so it appears in the recent-runs
panel.

`render.yml` renders selected clip ids or all new clips, subject to
`max_render_per_run`. `upload.yml` runs every 15 minutes, uploads at most one
clip, and uses the 13:00–05:00 Brussels window, rolling 25/day cap, and a
30-minute gap. (A 30-minute gap is deliberate: with 15-minute cron slots it
keeps 25/day attainable; 35 minutes would make the effective cadence 45
minutes and cap the day at about 21.) The preflight job is lightweight and
checks expiry/window/cap/gap before installing the full worker.

Upload order is:
1. Clips with `reddit_score` and `clip_created_at` within
   `reddit_priority_hours` (newest first).
2. All other approved clips by `clip_created_at DESC`.

The dashboard header shows uploads in the last 24 hours / the cap and the next
allowed upload time.

Before using the workflows:
1. Set `UPLOAD_MODE=api` in Vercel and redeploy.
2. Add GitHub repository secrets: `DATABASE_URL`, `TWITCH_CLIENT_ID`,
   `TWITCH_CLIENT_SECRET`, `BLOB_READ_WRITE_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`,
   `GOOGLE_OAUTH_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`, and optionally
   `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`.
3. Keep `TOKEN_ENCRYPTION_KEY` identical in Vercel and Actions.
4. Make sure the Vercel `GITHUB_TOKEN` has Actions read/write.

### Deploy to Vercel

1. Import the GitHub repo in Vercel and set **Root Directory** to `dashboard`.
   Framework preset: Next.js.
2. Add these environment variables (Production and Preview):
   `DATABASE_URL`, `DASHBOARD_PASSWORD`, `SESSION_SECRET`, `GITHUB_TOKEN`,
   `GITHUB_OWNER`, `GITHUB_REPO`, `UPLOAD_MODE`, `OWNER_NAME`,
   `CONTACT_EMAIL`, `CHANNEL_NAME`, `TWITCH_CLIENT_ID`,
   `TWITCH_CLIENT_SECRET`, `GOOGLE_OAUTH_CLIENT_ID`,
   `GOOGLE_OAUTH_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`, `APP_URL`, and
   optionally `REVIEWER_PASSWORD`.
   Generate `SESSION_SECRET` with `openssl rand -base64 32` and
   `TOKEN_ENCRYPTION_KEY` with `openssl rand -base64 32`. Use the same
   encryption key in the worker/GitHub Actions environment.
3. From the Vercel **Storage** tab, connect **Neon Postgres** and **Vercel
   Blob**. This injects `DATABASE_URL` and `BLOB_READ_WRITE_TOKEN`.
4. Create a fine-grained GitHub token with **Actions: read and write** on this
   repository only and use it as `GITHUB_TOKEN`.
5. Add `UPLOAD_MAX_PER_DAY=25`, `UPLOAD_WINDOW_START=13:00`,
   `UPLOAD_WINDOW_END=05:00`, `UPLOAD_TIMEZONE=Europe/Brussels`,
   `UPLOAD_MIN_GAP_MINUTES=30`, `UPLOAD_SLOT_MINUTES=15`,
   `DEFAULT_GAME_NAME=Grand Theft Auto VI`, and `DEFAULT_MIN_VIEWS=150` to
   Vercel so the header and fetch defaults match the worker config.
6. Push to `main`; Vercel deploys automatically. Add the matching GitHub
   repository secrets before using the run buttons.

## Database

`worker/migrations/001_init.sql` creates the `clips` table with statuses:

```
new -> downloaded -> rendered -> approved -> uploaded
new -> rejected
rendered -> rejected
failed -> new (retry)
```

Indexes exist on `status` and `streamer_login`.
