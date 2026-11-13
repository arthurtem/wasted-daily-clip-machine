CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'twitch',
    streamer_login TEXT NOT NULL,
    streamer_name TEXT NOT NULL,
    clip_title TEXT,
    clip_url TEXT NOT NULL,
    view_count INT,
    duration_s REAL,
    clip_created_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN (
            'new', 'downloaded', 'rendered', 'approved',
            'uploaded', 'rejected', 'failed'
        )),
    error TEXT,
    layout JSONB,
    blob_url TEXT,
    thumb_url TEXT,
    yt_title TEXT,
    yt_description TEXT,
    yt_tags TEXT[],
    youtube_video_id TEXT,
    reddit_score INT,
    reddit_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS clips_status_idx ON clips (status);
CREATE INDEX IF NOT EXISTS clips_streamer_login_idx ON clips (streamer_login);
