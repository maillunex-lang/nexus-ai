-- Human-reviewed Director proposals. Nothing in this schema executes commands.
CREATE TABLE IF NOT EXISTS director_proposals (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 task_id uuid NOT NULL REFERENCES mission_tasks(id) ON DELETE RESTRICT,
 created_by uuid NOT NULL REFERENCES users(id),
 plan jsonb NOT NULL,
 plan_digest text NOT NULL CHECK (length(plan_digest)=64),
 status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','denied','expired')),
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT (now()+interval '24 hours'),
 reviewed_by uuid REFERENCES users(id),
 reviewed_at timestamptz,
 CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS director_proposals_task_idx ON director_proposals(task_id,created_at DESC);
CREATE INDEX IF NOT EXISTS director_proposals_pending_idx ON director_proposals(status,expires_at);
INSERT INTO schema_migrations(version) VALUES ('006_director_approvals') ON CONFLICT DO NOTHING;
