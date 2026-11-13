CREATE TABLE IF NOT EXISTS youtube_connection (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    channel_id TEXT NOT NULL,
    channel_title TEXT NOT NULL,
    refresh_token_enc TEXT NOT NULL,
    scopes TEXT NOT NULL,
    connected_at TIMESTAMPTZ DEFAULT now()
);

DROP TABLE IF EXISTS youtube_settings;
