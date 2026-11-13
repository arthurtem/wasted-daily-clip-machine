CREATE TABLE IF NOT EXISTS youtube_settings (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    channel_title TEXT,
    token_ref TEXT,
    token_added_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
