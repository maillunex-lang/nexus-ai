CREATE TABLE IF NOT EXISTS user_sessions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 token_hash text NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 CONSTRAINT session_expiry CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS user_sessions_active_idx ON user_sessions(user_id, expires_at) WHERE revoked_at IS NULL;
CREATE TABLE IF NOT EXISTS login_attempts (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 username text NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now(),
 succeeded boolean NOT NULL
);
CREATE INDEX IF NOT EXISTS login_attempts_window_idx ON login_attempts(username,occurred_at DESC);
INSERT INTO schema_migrations(version) VALUES ('003_sessions') ON CONFLICT DO NOTHING;
