-- NEXUS AI 0.1 identity/authorization schema, no default accounts.
CREATE TABLE IF NOT EXISTS schema_migrations (
  version text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username text NOT NULL UNIQUE,
  password_hash text,
  disabled_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT username_valid CHECK (username ~ '^[a-z][a-z0-9_.-]{2,63}$')
);
CREATE TABLE IF NOT EXISTS roles (
  id text PRIMARY KEY,
  description text NOT NULL
);
INSERT INTO roles(id, description) VALUES
 ('owner','System owner'),('operator','Approved operator'),('viewer','Read-only viewer')
ON CONFLICT (id) DO NOTHING;
CREATE TABLE IF NOT EXISTS user_roles (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id text NOT NULL REFERENCES roles(id),
  PRIMARY KEY(user_id,role_id)
);
CREATE TABLE IF NOT EXISTS project_memberships (
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id text NOT NULL REFERENCES roles(id),
  PRIMARY KEY(project_id,user_id)
);
CREATE TABLE IF NOT EXISTS approval_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid REFERENCES projects(id),
  requested_by uuid REFERENCES users(id),
  action_type text NOT NULL,
  action_digest text NOT NULL CHECK (length(action_digest)=64),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','denied','expired','consumed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  resolved_by uuid REFERENCES users(id),
  resolved_at timestamptz,
  CONSTRAINT approval_expiry CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS approval_requests_pending_idx ON approval_requests(status,expires_at);
INSERT INTO schema_migrations(version) VALUES ('002_identity') ON CONFLICT DO NOTHING;
