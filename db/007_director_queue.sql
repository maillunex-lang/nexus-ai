-- Durable Director planning queue. Jobs never contain shell commands or credentials.
CREATE TABLE IF NOT EXISTS director_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 proposal_id uuid NOT NULL UNIQUE REFERENCES director_proposals(id) ON DELETE RESTRICT,
 requested_by uuid NOT NULL REFERENCES users(id),
 status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
 lease_until timestamptz,
 result jsonb,
 error_code text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS director_jobs_pending_idx ON director_jobs(status,created_at);
CREATE TABLE IF NOT EXISTS director_job_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 job_id uuid NOT NULL REFERENCES director_jobs(id) ON DELETE RESTRICT,
 event text NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations(version) VALUES ('007_director_queue') ON CONFLICT DO NOTHING;
