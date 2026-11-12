-- OAuth 2.1 storage foundation. Endpoints and token issuance are NOT enabled.
CREATE TABLE IF NOT EXISTS oauth_clients (
  client_id text PRIMARY KEY,
  client_name text NOT NULL,
  redirect_uris text[] NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  disabled_at timestamptz
);
CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
  code_hash text PRIMARY KEY,
  client_id text NOT NULL REFERENCES oauth_clients(client_id),
  user_id uuid NOT NULL REFERENCES users(id),
  redirect_uri text NOT NULL,
  code_challenge text NOT NULL,
  scope text NOT NULL DEFAULT '',
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pkce_s256_format CHECK (code_challenge ~ '^[A-Za-z0-9_-]{43}$')
);
CREATE INDEX IF NOT EXISTS oauth_codes_expiry_idx ON oauth_authorization_codes(expires_at);
CREATE TABLE IF NOT EXISTS oauth_access_tokens (
  token_hash text PRIMARY KEY,
  client_id text NOT NULL REFERENCES oauth_clients(client_id),
  user_id uuid NOT NULL REFERENCES users(id),
  audience text NOT NULL,
  scope text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS oauth_tokens_user_idx ON oauth_access_tokens(user_id,expires_at);
INSERT INTO schema_migrations(version) VALUES ('004_oauth_foundation') ON CONFLICT DO NOTHING;
