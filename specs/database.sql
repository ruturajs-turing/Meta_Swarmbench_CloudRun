-- AegisRun Foundry v2 reference schema.
-- SQLAlchemy models in api/app/models.py are authoritative for the local build.

create table users (
  id text primary key,
  username text not null unique,
  email text not null unique,
  display_name text not null,
  password_hash text not null,
  role text not null default 'trainer',
  state text not null default 'active',
  created_at timestamptz not null default now(),
  last_login_at timestamptz
);

create index users_username_idx on users(username);
create index users_email_idx on users(email);
create index users_state_idx on users(state);

create table session_tokens (
  token text primary key,
  user_id text not null references users(id),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index session_tokens_user_id_idx on session_tokens(user_id);

create table quotas (
  id text primary key,
  user_id text not null unique references users(id),
  max_active_runs integer not null default 2,
  max_queued_runs integer not null default 10,
  max_runtime_seconds integer not null default 7200,
  max_upload_mb integer not null default 2048,
  max_output_mb integer not null default 4096,
  max_monthly_cost double precision,
  parent_cpu integer not null default 2,
  parent_memory_mb integer not null default 6144,
  parent_disk_gb integer not null default 25
);

create table parent_sandboxes (
  id text primary key,
  user_id text not null references users(id),
  provider text not null default 'local-docker',
  state text not null default 'PROVISIONING',
  template_version text not null,
  container_id text,
  cpu integer not null default 2,
  memory_mb integer not null default 6144,
  disk_gb integer not null default 25,
  workspace_uri text not null,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  last_active_at timestamptz not null default now(),
  refresh_after_at timestamptz,
  paused_at timestamptz,
  error text
);

create index parent_sandboxes_user_id_idx on parent_sandboxes(user_id);
create index parent_sandboxes_state_idx on parent_sandboxes(state);

create table task_bundles (
  id text primary key,
  user_id text not null references users(id),
  parent_sandbox_id text not null references parent_sandboxes(id),
  name text not null,
  task_name text not null,
  uri text not null,
  workspace_uri text not null,
  size_bytes bigint not null default 0,
  sha256 text,
  task_toml text not null,
  state text not null default 'READY',
  created_at timestamptz not null default now()
);

create index task_bundles_user_id_idx on task_bundles(user_id);
create index task_bundles_parent_id_idx on task_bundles(parent_sandbox_id);

create table runs (
  id text primary key,
  user_id text not null references users(id),
  parent_sandbox_id text not null references parent_sandboxes(id),
  task_bundle_id text not null references task_bundles(id),
  state text not null default 'QUEUED',
  task_name text not null,
  task_toml text not null,
  normalized_spec jsonb not null,
  execution_mode text not null default 'harbor',
  resource_profile text not null,
  cpu integer not null,
  memory_mb integer not null,
  disk_gb integer not null,
  provider text not null default 'local-docker',
  container_id text,
  queued_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  duration_seconds integer,
  exit_code integer,
  passed boolean,
  failure_reason text,
  cost_estimate double precision not null default 0,
  artifact_uri text,
  cleanup_state text not null default 'PENDING',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index runs_user_id_idx on runs(user_id);
create index runs_parent_id_idx on runs(parent_sandbox_id);
create index runs_task_bundle_id_idx on runs(task_bundle_id);
create index runs_state_idx on runs(state);

create table run_events (
  id bigserial primary key,
  run_id text not null references runs(id) on delete cascade,
  sequence_number integer not null,
  ts timestamptz not null default now(),
  type text not null,
  stream text,
  message text,
  payload jsonb not null default '{}'::jsonb,
  unique (run_id, sequence_number)
);

create index run_events_run_id_idx on run_events(run_id);

create table artifacts (
  id text primary key,
  run_id text not null references runs(id) on delete cascade,
  kind text not null default 'result-package',
  path text not null,
  uri text not null,
  size_bytes bigint not null default 0,
  sha256 text,
  created_at timestamptz not null default now()
);

create index artifacts_run_id_idx on artifacts(run_id);

create table audit_logs (
  id bigserial primary key,
  actor_user_id text references users(id),
  action text not null,
  target_type text not null,
  target_id text,
  status text not null default 'SUCCESS',
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index audit_logs_actor_idx on audit_logs(actor_user_id);
create index audit_logs_action_idx on audit_logs(action);
create index audit_logs_target_idx on audit_logs(target_type, target_id);
create index audit_logs_created_at_idx on audit_logs(created_at);
