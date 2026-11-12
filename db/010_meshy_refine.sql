-- Separate owner-approved paid Refine operation. No automatic dispatch.
CREATE TABLE IF NOT EXISTS meshy_refine_requests (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 preview_request_id uuid NOT NULL REFERENCES meshy_requests(id) ON DELETE RESTRICT,
 created_by uuid NOT NULL REFERENCES users(id),
 max_credits integer NOT NULL CHECK (max_credits BETWEEN 10 AND 1000),
 status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
 dispatch_state text NOT NULL DEFAULT 'not_started'
 CHECK (dispatch_state IN ('not_started','dispatching','submitted','uncertain')),
 provider_task_id text UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT (now()+interval '30 minutes'),
 approved_at timestamptz,
 UNIQUE (preview_request_id)
);
INSERT INTO schema_migrations(version) VALUES ('010_meshy_refine') ON CONFLICT DO NOTHING;
