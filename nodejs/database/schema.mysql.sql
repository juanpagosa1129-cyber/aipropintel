create table if not exists users (
  id bigint primary key auto_increment,
  email varchar(190) not null unique,
  password_hash varchar(255) not null,
  role enum('admin','analyst','client') not null default 'admin',
  name varchar(190) not null,
  active boolean not null default true,
  created_at timestamp not null default current_timestamp
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists clients (
  id bigint primary key auto_increment,
  name varchar(190) not null,
  email varchar(190) not null unique,
  plan enum('starter','pro','enterprise') not null default 'starter',
  status enum('active','paused','cancelled') not null default 'active',
  monthly_price_cop int not null default 249000,
  created_at timestamp not null default current_timestamp
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists monitored_processes (
  id bigint primary key auto_increment,
  process_id varchar(80) not null unique,
  court varchar(255),
  city varchar(120),
  department varchar(120),
  jurisdiction varchar(120),
  process_type varchar(190),
  parties text,
  current_status text not null,
  last_update datetime,
  source_url varchar(500) not null,
  content_hash char(64) not null,
  risk_score decimal(5,2) not null default 0,
  first_seen_at timestamp not null default current_timestamp,
  updated_at timestamp not null default current_timestamp on update current_timestamp,
  fulltext idx_process_text (process_type, current_status, parties)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists process_snapshots (
  id bigint primary key auto_increment,
  process_id varchar(80) not null,
  content_hash char(64) not null,
  status_text text not null,
  raw json not null,
  captured_at timestamp not null default current_timestamp,
  unique key uq_snapshot (process_id, content_hash),
  constraint fk_snapshots_process foreign key (process_id)
    references monitored_processes(process_id) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists process_events (
  id bigint primary key auto_increment,
  process_id varchar(80) not null,
  event_type varchar(80) not null,
  severity tinyint not null,
  excerpt text not null,
  previous_hash char(64),
  current_hash char(64) not null,
  delivered_at datetime,
  created_at timestamp not null default current_timestamp,
  index idx_events_created (created_at, event_type),
  constraint fk_events_process foreign key (process_id)
    references monitored_processes(process_id) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists alert_deliveries (
  id bigint primary key auto_increment,
  event_id bigint not null,
  client_id bigint,
  channel enum('email','telegram','whatsapp','dashboard') not null default 'dashboard',
  status enum('pending','sent','failed') not null default 'pending',
  payload json not null,
  sent_at datetime,
  created_at timestamp not null default current_timestamp,
  index idx_alert_status (status, created_at),
  constraint fk_alert_event foreign key (event_id)
    references process_events(id) on delete cascade,
  constraint fk_alert_client foreign key (client_id)
    references clients(id) on delete set null
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists properties (
  id bigint primary key auto_increment,
  process_id varchar(80),
  matricula varchar(80),
  cadastral_code varchar(120),
  address varchar(255),
  city varchar(120),
  department varchar(120),
  appraisal_value decimal(18,2),
  area_m2 decimal(14,2),
  property_type varchar(120),
  lat decimal(10,7),
  lng decimal(10,7),
  raw json not null,
  created_at timestamp not null default current_timestamp,
  index idx_property_location (city, department),
  constraint fk_properties_process foreign key (process_id)
    references monitored_processes(process_id) on delete set null
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists crawl_jobs (
  id bigint primary key auto_increment,
  source_key varchar(80) not null,
  job_type varchar(40) not null,
  lookup_key varchar(190) not null,
  payload json not null,
  priority int not null default 100,
  status enum('queued','leased','done','failed','dead') not null default 'queued',
  attempts int not null default 0,
  max_attempts int not null default 5,
  run_after datetime not null default current_timestamp,
  leased_by varchar(190),
  leased_until datetime,
  last_error text,
  created_at timestamp not null default current_timestamp,
  updated_at timestamp not null default current_timestamp on update current_timestamp,
  unique key uq_job (source_key, job_type, lookup_key),
  index idx_jobs_pick (status, run_after, priority, id)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists source_rate_limits (
  source_key varchar(80) primary key,
  min_seconds_between_requests int not null,
  daily_limit int not null,
  day date not null,
  requests_today int not null default 0,
  last_request_at datetime
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists crawl_cache (
  cache_key char(64) primary key,
  source_key varchar(80) not null,
  lookup_key varchar(190) not null,
  content_hash char(64) not null,
  html mediumtext not null,
  metadata json not null,
  expires_at datetime not null,
  created_at timestamp not null default current_timestamp,
  updated_at timestamp not null default current_timestamp on update current_timestamp,
  index idx_cache_lookup (source_key, lookup_key, expires_at)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists audit_log (
  id bigint primary key auto_increment,
  actor varchar(190) not null,
  action varchar(100) not null,
  entity_type varchar(100) not null,
  entity_id varchar(190),
  lawful_basis varchar(190),
  purpose varchar(190),
  metadata json not null,
  created_at timestamp not null default current_timestamp,
  index idx_audit_created (created_at)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists privacy_review_items (
  id bigint primary key auto_increment,
  item_type varchar(80) not null,
  title varchar(190) not null,
  description text not null,
  severity enum('low','medium','high','critical') not null,
  status enum('open','reviewing','closed') not null default 'open',
  owner varchar(190),
  due_at datetime,
  metadata json not null,
  created_at timestamp not null default current_timestamp,
  closed_at datetime
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists data_subject_requests (
  id bigint primary key auto_increment,
  request_type enum('access','correction','deletion','objection','claim') not null,
  requester_name varchar(190),
  requester_contact varchar(190) not null,
  related_process_id varchar(80),
  status varchar(60) not null default 'received',
  response_due_at datetime,
  notes text,
  created_at timestamp not null default current_timestamp,
  closed_at datetime
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists watchlists (
  id bigint primary key auto_increment,
  client_id bigint,
  name varchar(190) not null,
  filters json not null,
  active boolean not null default true,
  created_at timestamp not null default current_timestamp,
  constraint fk_watchlists_client foreign key (client_id)
    references clients(id) on delete set null
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists app_settings (
  setting_key varchar(120) primary key,
  setting_value json not null,
  updated_at timestamp not null default current_timestamp on update current_timestamp
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;
