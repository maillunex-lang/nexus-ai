-- Meshy generation approval ledger. No worker executes approved records in this phase.
CREATE TABLE IF NOT EXISTS meshy_requests (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 created_by uuid NOT NULL REFERENCES users(id),
 proposal_sha256 text NOT NULL CHECK (length(proposal_sha256)=64),
 proposal jsonb NOT NULL,
 max_credits integer NOT NULL CHECK (max_credits BETWEEN 1 AND 1000),
 status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','cancelled')),
 approved_by uuid REFERENCES users(id),
 approved_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT (now()+interval '30 minutes'),
 CHECK ((status='approved')=(approved_by IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS meshy_requests_owner_idx ON meshy_requests(created_by,created_at DESC);
CREATE TABLE IF NOT EXISTS meshy_request_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 request_id uuid NOT NULL REFERENCES meshy_requests(id) ON DELETE RESTRICT,
 actor_id uuid NOT NULL REFERENCES users(id),
 action text NOT NULL CHECK (action IN ('created','approved','rejected','cancelled')),
 occurred_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations(version) VALUES ('008_meshy_requests') ON CONFLICT DO NOTHING;
