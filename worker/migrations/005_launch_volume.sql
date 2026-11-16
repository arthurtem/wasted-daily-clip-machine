ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS thumbnail_url TEXT,
    ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS auto_rendered_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reddit_id TEXT,
    ADD COLUMN IF NOT EXISTS reddit_subreddit TEXT,
    ADD COLUMN IF NOT EXISTS reddit_comments INT;

UPDATE clips
SET uploaded_at = updated_at
WHERE status = 'uploaded' AND uploaded_at IS NULL;

CREATE INDEX IF NOT EXISTS clips_uploaded_at_idx ON clips (uploaded_at);
CREATE INDEX IF NOT EXISTS clips_auto_rendered_at_idx ON clips (auto_rendered_at);

CREATE TABLE IF NOT EXISTS fetch_state (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    last_fetch_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
