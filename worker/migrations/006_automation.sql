CREATE TABLE IF NOT EXISTS automation_state (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    launch_date DATE,
    upload_cap INT NOT NULL DEFAULT 75,
    fetch_limit INT NOT NULL DEFAULT 20,
    render_limit INT NOT NULL DEFAULT 20,
    last_ramp_date DATE,
    last_upload_limit_at TIMESTAMPTZ,
    last_quota_error_at TIMESTAMPTZ,
    healthy_days INT NOT NULL DEFAULT 0,
    paused_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
