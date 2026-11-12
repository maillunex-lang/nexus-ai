-- Single-dispatch state for paid Meshy operations.
ALTER TABLE meshy_requests ADD COLUMN IF NOT EXISTS dispatch_state text NOT NULL DEFAULT 'not_started'
 CHECK (dispatch_state IN ('not_started','dispatching','submitted','uncertain','failed'));
ALTER TABLE meshy_requests ADD COLUMN IF NOT EXISTS provider_task_id text;
ALTER TABLE meshy_requests ADD COLUMN IF NOT EXISTS dispatch_started_at timestamptz;
ALTER TABLE meshy_requests ADD COLUMN IF NOT EXISTS error_code text;
CREATE UNIQUE INDEX IF NOT EXISTS meshy_requests_provider_task_unique
 ON meshy_requests(provider_task_id) WHERE provider_task_id IS NOT NULL;
INSERT INTO schema_migrations(version) VALUES ('009_meshy_dispatch') ON CONFLICT DO NOTHING;
