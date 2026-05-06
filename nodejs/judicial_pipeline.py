"""
Pipeline de produccion para monitoreo judicial responsable.

Comandos:
  python judicial_pipeline.py init-db
  python judicial_pipeline.py enqueue --seeds seeds.txt
  python judicial_pipeline.py worker --headless --max-jobs 100
  python judicial_pipeline.py once --seeds seeds.txt --headless

Variables:
  DATABASE_URL=postgresql://user:pass@localhost:5432/judicial_ai
  TELEGRAM_BOT_TOKEN=opcional
  TELEGRAM_CHAT_ID=opcional

El diseno usa una cola transaccional en PostgreSQL:
  - crawl_jobs: trabajos con lease, reintentos y prioridad.
  - source_rate_limits: cuota por fuente para evitar carga excesiva.
  - crawl_cache: cache TTL por consulta.
  - audit_log: trazabilidad operativa y de datos.
  - privacy_review_items: cola interna de cumplimiento.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


CPNU_RADICADO_URL = "https://consultaprocesos.ramajudicial.gov.co/Procesos/NumeroRadicacion"
SOURCE_KEY = "rama_judicial_cpnu"
USER_AGENT = "JudicialMonitor/2.0 contacto: cumplimiento@tuempresa.co"

DEFAULT_CACHE_TTL_HOURS = 12
DEFAULT_MIN_SECONDS_BETWEEN_REQUESTS = 8
DEFAULT_DAILY_LIMIT = 2000
DEFAULT_MAX_ATTEMPTS = 5

IMPORTANT_TERMS = {
    "embargo": 7,
    "secuestro": 8,
    "avaluo": 8,
    "avaluo aprobado": 9,
    "remate": 10,
    "liquidacion credito": 6,
    "sentencia": 5,
    "adjudicacion": 9,
    "pertenencia": 7,
    "hipotecario": 7,
    "mandamiento de pago": 6,
}

SCHEMA = """
create extension if not exists pg_trgm;

create table if not exists monitored_processes (
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

create table if not exists process_snapshots (
  id bigserial primary key,
  process_id text not null references monitored_processes(process_id) on delete cascade,
  content_hash text not null,
  status_text text not null,
  raw jsonb not null,
  captured_at timestamptz not null default now(),
  unique (process_id, content_hash)
);

create table if not exists process_events (
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

create table if not exists crawl_jobs (
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

create table if not exists source_rate_limits (
  source_key text primary key,
  min_seconds_between_requests int not null,
  daily_limit int not null,
  day date not null default current_date,
  requests_today int not null default 0,
  last_request_at timestamptz
);

create table if not exists crawl_cache (
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

create table if not exists audit_log (
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

create table if not exists privacy_review_items (
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

create table if not exists data_subject_requests (
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

create index if not exists idx_jobs_pick
  on crawl_jobs (status, run_after, priority, id);
create index if not exists idx_jobs_lookup
  on crawl_jobs (source_key, job_type, lookup_key);
create index if not exists idx_cache_expires
  on crawl_cache (source_key, lookup_key, expires_at);
create index if not exists idx_audit_created
  on audit_log (created_at desc);
create index if not exists idx_processes_status_trgm
  on monitored_processes using gin (current_status gin_trgm_ops);
create index if not exists idx_events_created
  on process_events (created_at desc, event_type);
"""


@dataclass
class Job:
    id: int
    source_key: str
    job_type: str
    lookup_key: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


@dataclass
class Snapshot:
    process_id: str
    court: str | None
    city: str | None
    process_type: str | None
    parties: str | None
    status_text: str
    last_update: datetime | None
    source_url: str
    raw: dict[str, Any]

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.raw, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize(text: str | None) -> str:
    text = text or ""
    return re.sub(r"\s+", " ", text).strip()


def cache_key(source_key: str, job_type: str, lookup_key: str) -> str:
    value = f"{source_key}:{job_type}:{lookup_key}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_date(value: str | None) -> datetime | None:
    value = normalize(value)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(value[:16], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def connect_db() -> psycopg.Connection:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Falta DATABASE_URL")
    return psycopg.connect(dsn, autocommit=False)


def audit(
    conn: psycopg.Connection,
    action: str,
    entity_type: str,
    entity_id: str | None,
    metadata: dict[str, Any] | None = None,
    actor: str = "system",
    lawful_basis: str = "public_judicial_information",
    purpose: str = "real_estate_judicial_monitoring",
) -> None:
    conn.execute(
        """
        insert into audit_log
          (actor, action, entity_type, entity_id, lawful_basis, purpose, metadata)
        values (%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            actor,
            action,
            entity_type,
            entity_id,
            lawful_basis,
            purpose,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )


def init_db(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA)
    conn.execute(
        """
        insert into source_rate_limits
          (source_key, min_seconds_between_requests, daily_limit)
        values (%s,%s,%s)
        on conflict (source_key) do nothing
        """,
        (SOURCE_KEY, DEFAULT_MIN_SECONDS_BETWEEN_REQUESTS, DEFAULT_DAILY_LIMIT),
    )
    seed_privacy_reviews(conn)
    audit(conn, "init_db", "system", SOURCE_KEY, {"host": socket.gethostname()})
    conn.commit()


def seed_privacy_reviews(conn: psycopg.Connection) -> None:
    items = [
        (
            "policy",
            "Definir politica de tratamiento de datos",
            "Publicar politica con finalidad, canales de derechos, retencion, seguridad y responsable.",
            "critical",
        ),
        (
            "rn_bases_datos",
            "Evaluar obligacion de RNBD",
            "Confirmar si la empresa debe inscribir bases de datos ante la SIC segun tamano y actividad.",
            "high",
        ),
        (
            "retention",
            "Aprobar tabla de retencion",
            "Definir cuanto tiempo se conservan snapshots, alertas y logs con base en finalidad comercial.",
            "high",
        ),
        (
            "contracts",
            "Contratos B2B con limites de uso",
            "Incluir prohibicion de asesoria legal automatica, reventa no autorizada y uso discriminatorio.",
            "high",
        ),
    ]
    for item_type, title, description, severity in items:
        exists = conn.execute(
            "select 1 from privacy_review_items where item_type = %s and title = %s",
            (item_type, title),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            insert into privacy_review_items
              (item_type, title, description, severity, due_at)
            values (%s,%s,%s,%s,%s)
            """,
            (item_type, title, description, severity, utcnow() + timedelta(days=14)),
        )


def load_seeds(path: str) -> list[str]:
    values: list[str] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "," in line:
                kind, value = line.split(",", 1)
                if kind.strip().lower() != "radicado":
                    continue
                line = value.strip()
            values.append(line)
    return values


def enqueue_seed(conn: psycopg.Connection, radicado: str, priority: int = 100) -> None:
    conn.execute(
        """
        insert into crawl_jobs
          (source_key, job_type, lookup_key, payload, priority, max_attempts)
        values (%s,'radicado',%s,%s,%s,%s)
        on conflict (source_key, job_type, lookup_key) do update set
          status = case
            when crawl_jobs.status in ('done','failed','dead') then 'queued'
            else crawl_jobs.status
          end,
          run_after = least(crawl_jobs.run_after, now()),
          priority = least(crawl_jobs.priority, excluded.priority),
          updated_at = now()
        """,
        (
            SOURCE_KEY,
            radicado,
            json.dumps({"lookup_basis": "client_watchlist_or_public_seed"}),
            priority,
            DEFAULT_MAX_ATTEMPTS,
        ),
    )
    audit(conn, "enqueue", "crawl_job", radicado, {"job_type": "radicado"})


def enqueue_file(conn: psycopg.Connection, seeds_path: str) -> int:
    count = 0
    for radicado in load_seeds(seeds_path):
        enqueue_seed(conn, radicado)
        count += 1
    conn.commit()
    return count


def lease_job(conn: psycopg.Connection, worker_id: str, lease_seconds: int = 300) -> Job | None:
    row = conn.execute(
        """
        with picked as (
          select id
          from crawl_jobs
          where status = 'queued'
            and run_after <= now()
          order by priority asc, id asc
          for update skip locked
          limit 1
        )
        update crawl_jobs j
        set status = 'leased',
            attempts = attempts + 1,
            leased_by = %s,
            leased_until = now() + (%s || ' seconds')::interval,
            updated_at = now()
        from picked
        where j.id = picked.id
        returning j.id, j.source_key, j.job_type, j.lookup_key, j.payload, j.attempts, j.max_attempts
        """,
        (worker_id, lease_seconds),
    ).fetchone()
    if not row:
        conn.commit()
        return None
    conn.commit()
    return Job(
        id=row[0],
        source_key=row[1],
        job_type=row[2],
        lookup_key=row[3],
        payload=row[4],
        attempts=row[5],
        max_attempts=row[6],
    )


def complete_job(conn: psycopg.Connection, job: Job) -> None:
    conn.execute(
        """
        update crawl_jobs
        set status = 'done', leased_by = null, leased_until = null, updated_at = now()
        where id = %s
        """,
        (job.id,),
    )
    audit(conn, "complete", "crawl_job", str(job.id), {"lookup_key": job.lookup_key})
    conn.commit()


def fail_job(conn: psycopg.Connection, job: Job, error: Exception) -> None:
    dead = job.attempts >= job.max_attempts
    backoff_minutes = min(240, 2**min(job.attempts, 8))
    jitter = random.randint(0, 60)
    status = "dead" if dead else "queued"
    conn.execute(
        """
        update crawl_jobs
        set status = %s,
            leased_by = null,
            leased_until = null,
            run_after = now() + (%s || ' seconds')::interval,
            last_error = %s,
            updated_at = now()
        where id = %s
        """,
        (status, backoff_minutes * 60 + jitter, str(error)[:1000], job.id),
    )
    audit(
        conn,
        "fail" if not dead else "dead_letter",
        "crawl_job",
        str(job.id),
        {"lookup_key": job.lookup_key, "error": str(error)[:500]},
    )
    conn.commit()


def wait_for_rate_limit(conn: psycopg.Connection, source_key: str) -> None:
    while True:
        row = conn.execute(
            """
            select min_seconds_between_requests, daily_limit, day, requests_today, last_request_at
            from source_rate_limits
            where source_key = %s
            for update
            """,
            (source_key,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"No existe rate limit para {source_key}")
        min_seconds, daily_limit, day, requests_today, last_request_at = row
        today = datetime.now().date()
        if day != today:
            requests_today = 0
            conn.execute(
                """
                update source_rate_limits
                set day = current_date, requests_today = 0
                where source_key = %s
                """,
                (source_key,),
            )
        if requests_today >= daily_limit:
            conn.commit()
            sleep_seconds = 60 * 30
            print(f"Cuota diaria agotada para {source_key}; esperando {sleep_seconds}s")
            time.sleep(sleep_seconds)
            continue
        if last_request_at:
            elapsed = (utcnow() - last_request_at).total_seconds()
            if elapsed < min_seconds:
                conn.commit()
                time.sleep(min_seconds - elapsed)
                continue
        conn.execute(
            """
            update source_rate_limits
            set requests_today = requests_today + 1,
                last_request_at = now()
            where source_key = %s
            """,
            (source_key,),
        )
        audit(conn, "rate_limit_consume", "source", source_key, {"daily_limit": daily_limit})
        conn.commit()
        return


def get_cache(conn: psycopg.Connection, job: Job) -> str | None:
    key = cache_key(job.source_key, job.job_type, job.lookup_key)
    row = conn.execute(
        """
        select html
        from crawl_cache
        where cache_key = %s and expires_at > now()
        """,
        (key,),
    ).fetchone()
    if row:
        audit(conn, "cache_hit", "crawl_cache", key, {"lookup_key": job.lookup_key})
        conn.commit()
        return row[0]
    audit(conn, "cache_miss", "crawl_cache", key, {"lookup_key": job.lookup_key})
    conn.commit()
    return None


def put_cache(conn: psycopg.Connection, job: Job, html: str, ttl_hours: int) -> None:
    key = cache_key(job.source_key, job.job_type, job.lookup_key)
    content_hash = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()
    conn.execute(
        """
        insert into crawl_cache
          (cache_key, source_key, lookup_key, content_hash, html, metadata, expires_at)
        values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (cache_key) do update set
          content_hash = excluded.content_hash,
          html = excluded.html,
          metadata = excluded.metadata,
          expires_at = excluded.expires_at,
          updated_at = now()
        """,
        (
            key,
            job.source_key,
            job.lookup_key,
            content_hash,
            html,
            json.dumps({"ttl_hours": ttl_hours, "source_url": CPNU_RADICADO_URL}),
            utcnow() + timedelta(hours=ttl_hours),
        ),
    )
    audit(conn, "cache_write", "crawl_cache", key, {"lookup_key": job.lookup_key})
    conn.commit()


def fill_first_available(page: Page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=1500):
                locator.fill(value)
                return True
        except PlaywrightTimeoutError:
            continue
    return False


def click_if_visible(page: Page, labels: list[str]) -> bool:
    for label in labels:
        locator = page.get_by_text(label, exact=False).first
        try:
            if locator.is_visible(timeout=1500):
                locator.click()
                return True
        except PlaywrightTimeoutError:
            continue
    return False


def fetch_cpnu_html(page: Page, radicado: str) -> str:
    page.goto(CPNU_RADICADO_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1200)
    filled = fill_first_available(
        page,
        [
            "input[name*='Numero']",
            "input[id*='Numero']",
            "input[placeholder*='radic']",
            "input[type='text']",
        ],
        radicado,
    )
    if not filled:
        raise RuntimeError("No se encontro el campo de radicado en CPNU")
    click_if_visible(page, ["Consultar", "Buscar", "Enviar"])
    page.wait_for_load_state("networkidle", timeout=45000)
    page.wait_for_timeout(1200)
    return page.content()


def extract_tables(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    for table in soup.find_all("table"):
        headers = [normalize(th.get_text(" ")) for th in table.find_all("th")]
        for tr in table.find_all("tr"):
            cells = [normalize(td.get_text(" ")) for td in tr.find_all("td")]
            if not cells:
                continue
            row: dict[str, str] = {}
            for idx, cell in enumerate(cells):
                key = headers[idx] if idx < len(headers) and headers[idx] else f"col_{idx}"
                row[key] = cell
            rows.append(row)
    return rows


def row_to_snapshot(row: dict[str, str], fallback_process_id: str, source_url: str) -> Snapshot:
    keys = {normalize(k).lower(): v for k, v in row.items()}
    process_id = (
        keys.get("radicado")
        or keys.get("numero de radicacion")
        or keys.get("proceso")
        or fallback_process_id
    )
    status = " | ".join(str(v) for v in row.values() if v)
    return Snapshot(
        process_id=normalize(process_id),
        court=keys.get("despacho") or keys.get("juzgado"),
        city=keys.get("ciudad") or keys.get("municipio"),
        process_type=keys.get("clase de proceso") or keys.get("tipo proceso"),
        parties=keys.get("sujetos procesales") or keys.get("demandante / demandado"),
        status_text=normalize(status),
        last_update=parse_date(keys.get("fecha actuacion") or keys.get("fecha de actuacion")),
        source_url=source_url,
        raw=row,
    )


def html_to_snapshots(html: str, fallback_process_id: str) -> list[Snapshot]:
    rows = extract_tables(html)
    if rows:
        return [row_to_snapshot(row, fallback_process_id, CPNU_RADICADO_URL) for row in rows]
    text = normalize(BeautifulSoup(html, "html.parser").get_text(" "))[:4000]
    return [
        Snapshot(
            process_id=fallback_process_id,
            court=None,
            city=None,
            process_type=None,
            parties=None,
            status_text=text,
            last_update=None,
            source_url=CPNU_RADICADO_URL,
            raw={"html_text": text},
        )
    ]


def detect_events(snapshot: Snapshot, previous_status: str | None, previous_hash: str | None) -> list[dict[str, Any]]:
    text = f"{snapshot.process_type or ''} {snapshot.status_text}".lower()
    changed = previous_hash != snapshot.content_hash
    events: list[dict[str, Any]] = []
    for term, severity in IMPORTANT_TERMS.items():
        was_present = bool(previous_status and term in previous_status.lower())
        if term in text and (changed or not was_present):
            pos = max(text.find(term) - 120, 0)
            events.append(
                {
                    "process_id": snapshot.process_id,
                    "event_type": term,
                    "severity": severity,
                    "excerpt": snapshot.status_text[pos : pos + 320],
                    "previous_hash": previous_hash,
                    "current_hash": snapshot.content_hash,
                }
            )
    return events


def upsert_snapshot(conn: psycopg.Connection, snapshot: Snapshot) -> list[dict[str, Any]]:
    old = conn.execute(
        "select current_status, content_hash from monitored_processes where process_id = %s",
        (snapshot.process_id,),
    ).fetchone()
    previous_status = old[0] if old else None
    previous_hash = old[1] if old else None
    risk_score = min(
        sum(score for term, score in IMPORTANT_TERMS.items() if term in snapshot.status_text.lower()),
        100,
    )
    conn.execute(
        """
        insert into monitored_processes
          (process_id, court, city, process_type, parties, current_status, last_update,
           source_url, content_hash, risk_score)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (process_id) do update set
          court = excluded.court,
          city = excluded.city,
          process_type = excluded.process_type,
          parties = excluded.parties,
          current_status = excluded.current_status,
          last_update = excluded.last_update,
          source_url = excluded.source_url,
          content_hash = excluded.content_hash,
          risk_score = excluded.risk_score,
          updated_at = now()
        """,
        (
            snapshot.process_id,
            snapshot.court,
            snapshot.city,
            snapshot.process_type,
            snapshot.parties,
            snapshot.status_text,
            snapshot.last_update,
            snapshot.source_url,
            snapshot.content_hash,
            risk_score,
        ),
    )
    conn.execute(
        """
        insert into process_snapshots (process_id, content_hash, status_text, raw)
        values (%s,%s,%s,%s)
        on conflict do nothing
        """,
        (
            snapshot.process_id,
            snapshot.content_hash,
            snapshot.status_text,
            json.dumps(snapshot.raw, ensure_ascii=False),
        ),
    )
    events = detect_events(snapshot, previous_status, previous_hash)
    for event in events:
        conn.execute(
            """
            insert into process_events
              (process_id, event_type, severity, excerpt, previous_hash, current_hash)
            values (%s,%s,%s,%s,%s,%s)
            """,
            (
                event["process_id"],
                event["event_type"],
                event["severity"],
                event["excerpt"],
                event["previous_hash"],
                event["current_hash"],
            ),
        )
        audit(conn, "event_detected", "process_event", snapshot.process_id, event)
    audit(
        conn,
        "snapshot_upsert",
        "monitored_process",
        snapshot.process_id,
        {"content_hash": snapshot.content_hash, "risk_score": risk_score},
    )
    conn.commit()
    return events


def send_telegram(event: dict[str, Any]) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    message = (
        "Alerta judicial inmobiliaria\n"
        f"Proceso: {event['process_id']}\n"
        f"Evento: {event['event_type']} | Severidad: {event['severity']}/10\n"
        f"Detalle: {event['excerpt'][:900]}"
    )
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message},
        timeout=20,
    )


def process_job(conn: psycopg.Connection, page: Page, job: Job, cache_ttl_hours: int) -> int:
    if job.job_type != "radicado":
        raise RuntimeError(f"job_type no soportado: {job.job_type}")
    html = get_cache(conn, job)
    if html is None:
        wait_for_rate_limit(conn, job.source_key)
        html = fetch_cpnu_html(page, job.lookup_key)
        put_cache(conn, job, html, cache_ttl_hours)
    snapshots = html_to_snapshots(html, job.lookup_key)
    event_count = 0
    for snapshot in snapshots:
        events = upsert_snapshot(conn, snapshot)
        event_count += len(events)
        for event in events:
            send_telegram(event)
    return event_count


def run_worker(args: argparse.Namespace) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    conn = connect_db()
    init_db(conn)
    processed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(user_agent=USER_AGENT, locale="es-CO", timezone_id="America/Bogota")
        page = context.new_page()
        while args.max_jobs <= 0 or processed < args.max_jobs:
            job = lease_job(conn, worker_id)
            if not job:
                if args.exit_when_empty:
                    break
                time.sleep(args.poll_seconds)
                continue
            try:
                events = process_job(conn, page, job, args.cache_ttl_hours)
                complete_job(conn, job)
                processed += 1
                print(f"OK job={job.id} lookup={job.lookup_key} events={events}")
            except Exception as exc:
                fail_job(conn, job, exc)
                print(f"ERROR job={job.id} lookup={job.lookup_key}: {exc}", file=sys.stderr)
        browser.close()
    conn.close()


def run_once(args: argparse.Namespace) -> None:
    conn = connect_db()
    init_db(conn)
    count = enqueue_file(conn, args.seeds)
    print(f"Encolados {count} trabajos")
    args.max_jobs = count
    args.exit_when_empty = True
    run_worker(args)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--seeds", default="seeds.txt")

    worker = sub.add_parser("worker")
    worker.add_argument("--headless", action="store_true")
    worker.add_argument("--max-jobs", type=int, default=0, help="0 = infinito")
    worker.add_argument("--exit-when-empty", action="store_true")
    worker.add_argument("--poll-seconds", type=float, default=10)
    worker.add_argument("--cache-ttl-hours", type=int, default=DEFAULT_CACHE_TTL_HOURS)

    once = sub.add_parser("once")
    once.add_argument("--seeds", default="seeds.txt")
    once.add_argument("--headless", action="store_true")
    once.add_argument("--poll-seconds", type=float, default=10)
    once.add_argument("--cache-ttl-hours", type=int, default=DEFAULT_CACHE_TTL_HOURS)

    args = parser.parse_args()
    if args.command == "init-db":
        conn = connect_db()
        init_db(conn)
        conn.close()
        print("Base inicializada")
    elif args.command == "enqueue":
        conn = connect_db()
        init_db(conn)
        count = enqueue_file(conn, args.seeds)
        conn.close()
        print(f"Encolados {count} trabajos")
    elif args.command == "worker":
        run_worker(args)
    elif args.command == "once":
        run_once(args)


if __name__ == "__main__":
    main()
