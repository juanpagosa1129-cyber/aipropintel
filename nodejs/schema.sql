create extension if not exists postgis;
create extension if not exists pg_trgm;

create table clients (
  id bigserial primary key,
  name text not null,
  email text unique not null,
  plan text not null check (plan in ('starter','pro','enterprise')),
  status text not null default 'active',
  created_at timestamptz not null default now()
);

create table monitored_processes (
  id bigserial primary key,
  process_id text unique not null,
  court text,
  city text,
  department text,
  jurisdiction text,
  process_type text,
  parties text,
  current_status text not null,
  last_update timestamptz,
  source_url text not null,
  content_hash text not null,
  risk_score numeric(5,2) not null default 0,
  first_seen_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table process_snapshots (
  id bigserial primary key,
  process_id text not null references monitored_processes(process_id) on delete cascade,
  content_hash text not null,
  status_text text not null,
  raw jsonb not null,
  captured_at timestamptz not null default now(),
  unique (process_id, content_hash)
);

create table process_events (
  id bigserial primary key,
  process_id text not null references monitored_processes(process_id) on delete cascade,
  event_type text not null,
  severity int not null check (severity between 1 and 10),
  excerpt text not null,
  previous_hash text,
  current_hash text not null,
  created_at timestamptz not null default now(),
  delivered_at timestamptz
);

create table crawl_jobs (
  id bigserial primary key,
  source_key text not null,
  job_type text not null,
  lookup_key text not null,
  payload jsonb not null default '{}'::jsonb,
  priority int not null default 100,
  status text not null default 'queued'
    check (status in ('queued','leased','done','failed','dead')),
  attempts int not null default 0,
  max_attempts int not null default 5,
  run_after timestamptz not null default now(),
  leased_by text,
  leased_until timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_key, job_type, lookup_key)
);

create table source_rate_limits (
  source_key text primary key,
  min_seconds_between_requests int not null,
  daily_limit int not null,
  day date not null default current_date,
  requests_today int not null default 0,
  last_request_at timestamptz
);

create table crawl_cache (
  cache_key text primary key,
  source_key text not null,
  lookup_key text not null,
  content_hash text not null,
  html text not null,
  metadata jsonb not null default '{}'::jsonb,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table audit_log (
  id bigserial primary key,
  actor text not null,
  action text not null,
  entity_type text not null,
  entity_id text,
  lawful_basis text,
  purpose text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table privacy_review_items (
  id bigserial primary key,
  item_type text not null,
  title text not null,
  description text not null,
  severity text not null check (severity in ('low','medium','high','critical')),
  status text not null default 'open' check (status in ('open','reviewing','closed')),
  owner text,
  due_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  closed_at timestamptz
);

create table data_subject_requests (
  id bigserial primary key,
  request_type text not null
    check (request_type in ('access','correction','deletion','objection','claim')),
  requester_name text,
  requester_contact text not null,
  related_process_id text,
  status text not null default 'received',
  response_due_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  closed_at timestamptz
);

create table properties (
  id bigserial primary key,
  process_id text references monitored_processes(process_id) on delete set null,
  matricula text,
  cadastral_code text,
  address text,
  city text,
  department text,
  appraisal_value numeric(18,2),
  area_m2 numeric(14,2),
  property_type text,
  geom geometry(Point, 4326),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table opportunity_scores (
  id bigserial primary key,
  process_id text not null references monitored_processes(process_id) on delete cascade,
  property_id bigint references properties(id) on delete set null,
  score numeric(5,2) not null,
  model_version text not null,
  factors jsonb not null,
  predicted_outcome text,
  created_at timestamptz not null default now()
);

create table client_watchlists (
  id bigserial primary key,
  client_id bigint not null references clients(id) on delete cascade,
  name text not null,
  filters jsonb not null,
  created_at timestamptz not null default now()
);

create table alert_deliveries (
  id bigserial primary key,
  event_id bigint not null references process_events(id) on delete cascade,
  client_id bigint not null references clients(id) on delete cascade,
  channel text not null check (channel in ('email','telegram','whatsapp','dashboard')),
  status text not null default 'pending',
  payload jsonb not null,
  sent_at timestamptz
);

create index idx_processes_type_trgm on monitored_processes using gin (process_type gin_trgm_ops);
create index idx_processes_status_trgm on monitored_processes using gin (current_status gin_trgm_ops);
create index idx_process_events_type_created on process_events (event_type, created_at desc);
create index idx_jobs_pick on crawl_jobs (status, run_after, priority, id);
create index idx_cache_expires on crawl_cache (source_key, lookup_key, expires_at);
create index idx_audit_created on audit_log (created_at desc);
create index idx_properties_geom on properties using gist (geom);
create index idx_scores_score on opportunity_scores (score desc);
