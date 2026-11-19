ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS moderation_level TEXT,
    ADD COLUMN IF NOT EXISTS moderation_score REAL,
    ADD COLUMN IF NOT EXISTS moderation_labels TEXT;

CREATE INDEX IF NOT EXISTS clips_youtube_video_id_idx ON clips (youtube_video_id);
