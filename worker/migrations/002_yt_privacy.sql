ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS yt_privacy TEXT NOT NULL DEFAULT 'public'
        CHECK (yt_privacy IN ('public', 'unlisted', 'private'));
