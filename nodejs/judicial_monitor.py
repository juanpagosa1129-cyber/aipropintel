"""
Monitor judicial inmobiliario para Colombia.

Uso:
  pip install playwright beautifulsoup4 psycopg[binary] python-dotenv
  python -m playwright install chromium
  $env:DATABASE_URL="postgresql://user:pass@localhost:5432/judicial_ai"
  $env:TELEGRAM_BOT_TOKEN="..."
  $env:TELEGRAM_CHAT_ID="..."
  python judicial_monitor.py --seeds seeds.txt --headless

Notas:
  - Diseñado para consultas públicas y carga moderada.
  - No evade captchas, bloqueos ni controles de acceso.
  - Ajusta selectores si la CPNU cambia su interfaz.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import psycopg
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


CPNU_URL = "https://consultaprocesos.ramajudicial.gov.co/Procesos/Index"
RADICADO_URL = "https://consultaprocesos.ramajudicial.gov.co/Procesos/NumeroRadicacion"
USER_AGENT = "JudicialMonitor/1.0 contacto: operaciones@tuempresa.co"

IMPORTANT_TERMS = {
    "embargo": 7,
    "secuestro": 8,
    "avaluo": 8,
    "avalúo": 8,
    "remate": 10,
    "liquidacion credito": 6,
    "liquidación crédito": 6,
    "sentencia": 5,
    "adjudicacion": 9,
    "adjudicación": 9,
    "pertenencia": 7,
    "hipotecario": 7,
    "mandamiento de pago": 6,
}


@dataclass
class Seed:
    kind: str
    value: str


@dataclass
class CaseSnapshot:
    process_id: str
    court: str | None
    city: str | None
    process_type: str | None
    parties: str | None
    status_text: str
    last_update: datetime | None
    source_url: str
    raw: dict

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.raw, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize(text: str | None) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date(text: str | None) -> datetime | None:
    text = normalize(text)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text[:16], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def load_seeds(path: str) -> list[Seed]:
    seeds: list[Seed] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "," in line:
                kind, value = line.split(",", 1)
            else:
                kind, value = "radicado", line
            seeds.append(Seed(kind=kind.strip().lower(), value=value.strip()))
    return seeds


def connect_db() -> psycopg.Connection:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Falta DATABASE_URL")
    return psycopg.connect(dsn)


def ensure_tables(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        create table if not exists monitored_processes (
          id bigserial primary key,
          process_id text unique not null,
          court text,
          city text,
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
          process_id text not null,
          content_hash text not null,
          status_text text not null,
          raw jsonb not null,
          captured_at timestamptz not null default now(),
          unique (process_id, content_hash)
        );
        create table if not exists process_events (
          id bigserial primary key,
          process_id text not null,
          event_type text not null,
          severity int not null,
          excerpt text not null,
          previous_hash text,
          current_hash text not null,
          created_at timestamptz not null default now(),
          delivered_at timestamptz
        );
        """
    )
    conn.commit()


def click_if_visible(page: Page, labels: Iterable[str]) -> bool:
    for label in labels:
        locator = page.get_by_text(label, exact=False).first
        try:
            if locator.is_visible(timeout=1500):
                locator.click()
                return True
        except PlaywrightTimeoutError:
            continue
    return False


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


def extract_tables(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for table in soup.find_all("table"):
        headers = [normalize(th.get_text(" ")) for th in table.find_all("th")]
        for tr in table.find_all("tr"):
            cells = [normalize(td.get_text(" ")) for td in tr.find_all("td")]
            if not cells:
                continue
            row = {}
            for idx, value in enumerate(cells):
                key = headers[idx] if idx < len(headers) and headers[idx] else f"col_{idx}"
                row[key] = value
            rows.append(row)
    return rows


def row_to_snapshot(row: dict, fallback_process_id: str, source_url: str) -> CaseSnapshot:
    keys = {normalize(k).lower(): v for k, v in row.items()}
    process_id = (
        keys.get("radicado")
        or keys.get("numero de radicacion")
        or keys.get("número de radicación")
        or keys.get("proceso")
        or fallback_process_id
    )
    status = " | ".join(str(v) for v in row.values() if v)
    return CaseSnapshot(
        process_id=normalize(process_id),
        court=keys.get("despacho") or keys.get("juzgado"),
        city=keys.get("ciudad") or keys.get("municipio"),
        process_type=keys.get("clase de proceso") or keys.get("tipo proceso"),
        parties=keys.get("sujetos procesales") or keys.get("demandante / demandado"),
        status_text=normalize(status),
        last_update=parse_date(keys.get("fecha actuacion") or keys.get("fecha de actuación")),
        source_url=source_url,
        raw=row,
    )


def scrape_by_radicado(page: Page, radicado: str) -> list[CaseSnapshot]:
    page.goto(RADICADO_URL, wait_until="domcontentloaded", timeout=45000)
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
        raise RuntimeError("No se encontró el campo de radicado en CPNU")
    click_if_visible(page, ["Consultar", "Buscar", "Enviar"])
    page.wait_for_load_state("networkidle", timeout=45000)
    page.wait_for_timeout(1200)
    rows = extract_tables(page.content())
    return [row_to_snapshot(row, radicado, page.url) for row in rows] or [
        CaseSnapshot(
            process_id=radicado,
            court=None,
            city=None,
            process_type=None,
            parties=None,
            status_text=normalize(BeautifulSoup(page.content(), "html.parser").get_text(" "))[:4000],
            last_update=None,
            source_url=page.url,
            raw={"html_text": normalize(BeautifulSoup(page.content(), "html.parser").get_text(" "))[:4000]},
        )
    ]


def detect_events(snapshot: CaseSnapshot, previous_status: str | None, previous_hash: str | None) -> list[dict]:
    text = f"{snapshot.process_type or ''} {snapshot.status_text}".lower()
    events = []
    changed = previous_hash != snapshot.content_hash
    for term, severity in IMPORTANT_TERMS.items():
        if term in text and (changed or not previous_status or term not in previous_status.lower()):
            start = max(text.find(term) - 120, 0)
            excerpt = snapshot.status_text[start : start + 320]
            events.append(
                {
                    "process_id": snapshot.process_id,
                    "event_type": term,
                    "severity": severity,
                    "excerpt": excerpt,
                    "previous_hash": previous_hash,
                    "current_hash": snapshot.content_hash,
                }
            )
    return events


def upsert_snapshot(conn: psycopg.Connection, snapshot: CaseSnapshot) -> list[dict]:
    old = conn.execute(
        "select current_status, content_hash from monitored_processes where process_id = %s",
        (snapshot.process_id,),
    ).fetchone()
    previous_status = old[0] if old else None
    previous_hash = old[1] if old else None
    risk_score = min(sum(score for term, score in IMPORTANT_TERMS.items() if term in snapshot.status_text.lower()), 100)
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
        (snapshot.process_id, snapshot.content_hash, snapshot.status_text, json.dumps(snapshot.raw, ensure_ascii=False)),
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
    conn.commit()
    return events


def send_telegram(event: dict) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    message = (
        f"Alerta judicial inmobiliaria\n"
        f"Proceso: {event['process_id']}\n"
        f"Evento: {event['event_type']} | Severidad: {event['severity']}/10\n"
        f"Detalle: {event['excerpt'][:900]}"
    )
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message},
        timeout=20,
    )


def run_monitor(seeds: list[Seed], headless: bool, delay: float) -> None:
    conn = connect_db()
    ensure_tables(conn)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=USER_AGENT, locale="es-CO", timezone_id="America/Bogota")
        page = context.new_page()
        total_events = 0
        for seed in seeds:
            if seed.kind != "radicado":
                print(f"Saltando seed no implementada en esta versión: {seed.kind},{seed.value}")
                continue
            try:
                snapshots = scrape_by_radicado(page, seed.value)
                for snapshot in snapshots:
                    events = upsert_snapshot(conn, snapshot)
                    total_events += len(events)
                    for event in events:
                        send_telegram(event)
                print(f"OK {seed.value}: {len(snapshots)} registros, {total_events} alertas acumuladas")
            except Exception as exc:
                print(f"ERROR {seed.value}: {exc}", file=sys.stderr)
            time.sleep(delay)
        browser.close()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="seeds.txt", help="Archivo con radicados o tipo,valor")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay", type=float, default=8.0, help="Segundos entre consultas")
    args = parser.parse_args()
    run_monitor(load_seeds(args.seeds), headless=args.headless, delay=args.delay)


if __name__ == "__main__":
    main()
