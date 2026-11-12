-- Mission Control: durable, auditable task records. No automatic command execution.
CREATE TABLE IF NOT EXISTS mission_tasks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
 title text NOT NULL CHECK (length(trim(title)) BETWEEN 3 AND 200),
 description text NOT NULL DEFAULT '' CHECK (length(description)<=10000),
 status text NOT NULL DEFAULT 'backlog' CHECK (status IN ('backlog','ready','in_progress','blocked','done','cancelled')),
 assigned_agent text CHECK (assigned_agent IN ('director','developer','tester','devops','artist')),
 created_by uuid NOT NULL REFERENCES users(id),
 updated_by uuid NOT NULL REFERENCES users(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 version integer NOT NULL DEFAULT 1 CHECK (version>0)
);
CREATE INDEX IF NOT EXISTS mission_tasks_project_idx ON mission_tasks(project_id,created_at DESC);
CREATE INDEX IF NOT EXISTS mission_tasks_status_idx ON mission_tasks(status);
CREATE TABLE IF NOT EXISTS mission_task_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 task_id uuid NOT NULL REFERENCES mission_tasks(id) ON DELETE RESTRICT,
 actor_id uuid NOT NULL REFERENCES users(id),
 event_type text NOT NULL,
 old_status text,
 new_status text,
 occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mission_task_events_task_idx ON mission_task_events(task_id,occurred_at DESC);
INSERT INTO schema_migrations(version) VALUES ('005_mission_control') ON CONFLICT DO NOTHING;
