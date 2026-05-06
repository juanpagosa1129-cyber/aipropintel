from __future__ import annotations

import json
import mimetypes
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from propintel.config import Settings
from propintel.database import Database
from propintel.sources.csv_source import parse_csv_text
from propintel.sources.rama_judicial import InteractiveControlRequired, RamaJudicialSource

settings = Settings.from_env(ROOT)
db = Database(settings.database_path)
db.initialize()
adapter = RamaJudicialSource(settings)

DEFAULT_QUERIES = [
    {"ciudad": "Bogota", "tipo_proceso": "Ejecutivo hipotecario", "limit": 40},
    {"ciudad": "Medellin", "tipo_proceso": "Ejecutivo singular", "limit": 40},
    {"ciudad": "Cali", "tipo_proceso": "Ejecutivo hipotecario", "limit": 40},
]


class BotState:
    def __init__(self):
        self.interval_minutes = 24 * 60
        self.enabled = True
        self.last_run_at = None
        self.last_status = "idle"
        self.last_message = "Sin ejecuciones aun"
        self.last_imported = 0
        self.queries = list(DEFAULT_QUERIES)
        self.lock = threading.Lock()


bot_state = BotState()


def json_response(handler: BaseHTTPRequestHandler, payload, status: int = 200):
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: BaseHTTPRequestHandler):
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length == 0:
        return {}
    body = handler.rfile.read(length).decode("utf-8")
    return json.loads(body or "{}")


def to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def normalize_process(record: dict) -> dict:
    aliases = {
        "numero": "numero_proceso",
        "proceso": "numero_proceso",
        "tipo": "tipo_proceso",
        "avaluo_cop": "avaluo",
        "edad_proceso": "edad_meses",
        "numero_demandados": "demandados",
        "numero_acreedores": "acreedores",
    }
    normalized = {aliases.get(k, k): v for k, v in record.items()}
    normalized["direccion"] = str(normalized.get("direccion") or "Direccion no informada").strip()

    required = ["numero_proceso", "ciudad", "tipo_proceso", "estado"]
    missing = [key for key in required if not str(normalized.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Campos obligatorios faltantes: {', '.join(missing)}")
    return normalized


def run_official_query(query: dict, mode: str) -> dict:
    try:
        records = adapter.fetch(query)
        normalized = [normalize_process(item) for item in records]
        saved = db.bulk_upsert(normalized, source="rama_judicial")
        run = db.record_source_run(
            source="rama_judicial",
            mode=mode,
            status="ok",
            query=query,
            imported_count=len(saved),
            message=f"Consulta oficial completada. Registros importados: {len(saved)}",
            requires_human_intervention=False,
        )
        return {"status": "ok", "imported": len(saved), "items": saved, "run": run}
    except InteractiveControlRequired as exc:
        run = db.record_source_run(
            source="rama_judicial",
            mode=mode,
            status="blocked_interactive",
            query=query,
            imported_count=0,
            message=str(exc),
            requires_human_intervention=True,
        )
        return {"status": "blocked_interactive", "imported": 0, "items": [], "run": run, "message": str(exc)}
    except Exception as exc:
        run = db.record_source_run(
            source="rama_judicial",
            mode=mode,
            status="error",
            query=query,
            imported_count=0,
            message=str(exc),
            requires_human_intervention=False,
        )
        return {"status": "error", "imported": 0, "items": [], "run": run, "message": str(exc)}


def run_bot_cycle():
    total_imported = 0
    final_status = "ok"
    final_message = "Ejecucion automatica completada."
    for query in list(bot_state.queries):
        result = run_official_query(query, mode="scheduled")
        total_imported += int(result.get("imported") or 0)
        if result["status"] == "blocked_interactive":
            final_status = "blocked_interactive"
            final_message = result.get("message", "Bloqueado por control interactivo.")
            break
        if result["status"] == "error":
            final_status = "error"
            final_message = result.get("message", "Error en fuente oficial.")
            break
    with bot_state.lock:
        bot_state.last_run_at = datetime.now(UTC).isoformat()
        bot_state.last_status = final_status
        bot_state.last_message = final_message
        bot_state.last_imported = total_imported


def bot_loop():
    while True:
        time.sleep(5)
        with bot_state.lock:
            enabled = bot_state.enabled
            interval_seconds = max(60, int(bot_state.interval_minutes) * 60)
            last = bot_state.last_run_at
        if not enabled:
            continue
        now = datetime.now(UTC)
        should_run = last is None
        if last is not None:
            try:
                last_dt = datetime.fromisoformat(last)
                should_run = (now - last_dt).total_seconds() >= interval_seconds
            except ValueError:
                should_run = True
        if should_run:
            run_bot_cycle()


def sse_payload():
    analytics = db.analytics()
    source = db.source_status()
    with bot_state.lock:
        bot = {
            "enabled": bot_state.enabled,
            "interval_minutes": bot_state.interval_minutes,
            "last_run_at": bot_state.last_run_at,
            "last_status": bot_state.last_status,
            "last_imported": bot_state.last_imported,
        }
    return {"ts": datetime.now(UTC).isoformat(), "analytics": analytics, "source_status": source, "bot": bot}


class Handler(BaseHTTPRequestHandler):
    server_version = "PropintelIA/3.0"

    def do_OPTIONS(self):
        json_response(self, {"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/health":
            with bot_state.lock:
                bot = {
                    "enabled": bot_state.enabled,
                    "interval_minutes": bot_state.interval_minutes,
                    "last_run_at": bot_state.last_run_at,
                    "last_status": bot_state.last_status,
                    "last_message": bot_state.last_message,
                    "last_imported": bot_state.last_imported,
                }
            json_response(self, {"status": "ok", "database": str(settings.database_path), "bot": bot})
            return

        if path == "/api/processes":
            city = query.get("city", [""])[0] or None
            risk = query.get("risk", [""])[0] or None
            status = query.get("status", [""])[0] or None
            process_type = query.get("type", [""])[0] or None
            text = query.get("q", [""])[0] or None
            limit = to_int(query.get("limit", ["200"])[0], 200)
            offset = to_int(query.get("offset", ["0"])[0], 0)
            items = db.list_processes(
                city=city,
                risk=risk,
                status=status,
                process_type=process_type,
                text=text,
                limit=limit,
                offset=offset,
            )
            total = db.count_processes(
                city=city,
                risk=risk,
                status=status,
                process_type=process_type,
                text=text,
            )
            json_response(self, {"items": items, "count": len(items), "total": total, "offset": offset, "limit": limit})
            return

        if path == "/api/processes/detail":
            numero = query.get("numero_proceso", [""])[0]
            if not numero:
                json_response(self, {"error": "numero_proceso es obligatorio"}, 400)
                return
            item = db.get_process_by_number(numero)
            if not item:
                json_response(self, {"error": "Proceso no encontrado"}, 404)
                return
            json_response(self, {"item": item})
            return

        if path == "/api/opportunities":
            min_score = to_int(query.get("min_score", ["70"])[0], 70)
            limit = to_int(query.get("limit", ["80"])[0], 80)
            json_response(self, {"items": db.list_opportunities(min_score=min_score, limit=limit)})
            return

        if path == "/api/alerts":
            limit = to_int(query.get("limit", ["300"])[0], 300)
            json_response(self, {"items": db.list_alerts(limit=limit)})
            return

        if path == "/api/events":
            limit = to_int(query.get("limit", ["50"])[0], 50)
            json_response(self, {"items": db.list_events(limit=limit)})
            return

        if path == "/api/analytics":
            json_response(self, db.analytics())
            return

        if path == "/api/source/status":
            json_response(self, db.source_status())
            return

        if path == "/api/source/runs":
            limit = to_int(query.get("limit", ["30"])[0], 30)
            json_response(self, {"items": db.list_source_runs(limit=limit)})
            return

        if path == "/api/bot/config":
            with bot_state.lock:
                json_response(
                    self,
                    {
                        "enabled": bot_state.enabled,
                        "interval_minutes": bot_state.interval_minutes,
                        "queries": bot_state.queries,
                        "last_run_at": bot_state.last_run_at,
                        "last_status": bot_state.last_status,
                        "last_message": bot_state.last_message,
                        "last_imported": bot_state.last_imported,
                    },
                )
            return

        if path == "/api/business/projection":
            basic = to_int(query.get("basic", ["100"])[0], 100)
            pro = to_int(query.get("pro", ["30"])[0], 30)
            enterprise = to_int(query.get("enterprise", ["10"])[0], 10)
            ticket = to_int(query.get("enterprise_ticket", ["3000000"])[0], 3000000)
            json_response(self, db.business_projection(basic, pro, enterprise, ticket))
            return

        if path == "/api/watchlists":
            owner = query.get("owner", [""])[0] or None
            json_response(self, {"items": db.list_watchlists(owner=owner)})
            return

        if path == "/api/stream/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                for _ in range(180):
                    payload = sse_payload()
                    chunk = f"event: state\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(2)
            except Exception:
                return
            return

        self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/processes":
                payload = normalize_process(read_json(self))
                saved = db.upsert_process(payload)
                json_response(self, {"item": saved}, 201)
                return

            if path == "/api/import/csv":
                payload = read_json(self)
                csv_text = payload.get("csv_text", "")
                if not csv_text:
                    json_response(self, {"error": "Debe enviar csv_text"}, 400)
                    return
                records = [normalize_process(item) for item in parse_csv_text(csv_text)]
                saved = db.bulk_upsert(records, source="csv_import")
                json_response(self, {"imported": len(saved), "items": saved}, 201)
                return

            if path == "/api/live/search":
                payload = read_json(self)
                result = run_official_query(payload, mode="manual_live")
                code = 200 if result["status"] == "ok" else 202
                json_response(self, result, code)
                return

            if path == "/api/bot/run-now":
                run_bot_cycle()
                with bot_state.lock:
                    json_response(
                        self,
                        {
                            "ok": True,
                            "last_run_at": bot_state.last_run_at,
                            "last_status": bot_state.last_status,
                            "last_message": bot_state.last_message,
                            "last_imported": bot_state.last_imported,
                        },
                    )
                return

            if path == "/api/bot/config":
                payload = read_json(self)
                with bot_state.lock:
                    if "enabled" in payload:
                        bot_state.enabled = bool(payload["enabled"])
                    if "interval_minutes" in payload:
                        bot_state.interval_minutes = max(5, int(payload["interval_minutes"]))
                    if "queries" in payload and isinstance(payload["queries"], list):
                        bot_state.queries = payload["queries"]
                json_response(
                    self,
                    {
                        "enabled": bot_state.enabled,
                        "interval_minutes": bot_state.interval_minutes,
                        "queries": bot_state.queries,
                    },
                )
                return

            if path == "/api/crawler/run":
                payload = read_json(self)
                source = payload.get("source", "rama_judicial")
                if source != "rama_judicial":
                    json_response(self, {"error": f"Fuente no soportada: {source}"}, 400)
                    return
                result = run_official_query(payload, mode="manual_crawler")
                code = 200 if result["status"] == "ok" else 202
                json_response(self, result, code)
                return

            if path == "/api/watchlists":
                payload = read_json(self)
                name = str(payload.get("name") or "").strip()
                owner = str(payload.get("owner") or "equipo").strip()
                criteria = payload.get("criteria") or {}
                if not name:
                    json_response(self, {"error": "name es obligatorio"}, 400)
                    return
                watchlist = db.create_watchlist(name=name, owner=owner, criteria=criteria, active=True)
                json_response(self, {"item": watchlist}, 201)
                return

            if path == "/api/watchlists/run":
                payload = read_json(self)
                watchlist_id = to_int(payload.get("id"), 0)
                if watchlist_id <= 0:
                    json_response(self, {"error": "id invalido"}, 400)
                    return
                result = db.run_watchlist(watchlist_id, limit=to_int(payload.get("limit"), 100))
                json_response(self, result)
                return

            if path == "/api/watchlists/delete":
                payload = read_json(self)
                watchlist_id = to_int(payload.get("id"), 0)
                if watchlist_id <= 0:
                    json_response(self, {"error": "id invalido"}, 400)
                    return
                ok = db.delete_watchlist(watchlist_id)
                json_response(self, {"ok": ok})
                return

            json_response(self, {"error": "Ruta no encontrada"}, 404)
        except ValueError as exc:
            json_response(self, {"error": str(exc)}, 400)
        except Exception as exc:
            json_response(self, {"error": "Error interno", "detail": str(exc)}, 500)

    def serve_static(self, path: str):
        if path == "/":
            path = "/index.html"
        target = (settings.frontend_dir / path.lstrip("/")).resolve()
        frontend_root = settings.frontend_dir.resolve()

        if not str(target).startswith(str(frontend_root)):
            json_response(self, {"error": "Forbidden"}, 403)
            return
        if not target.exists() or not target.is_file():
            target = frontend_root / "index.html"

        content = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    thread = threading.Thread(target=bot_loop, daemon=True)
    thread.start()
    server = ThreadingHTTPServer((settings.host, settings.port), Handler)
    print(f"Propintel IA listo en http://{settings.host}:{settings.port}")
    print(f"Base de datos: {settings.database_path}")
    server.serve_forever()


if __name__ == "__main__":
    main()
