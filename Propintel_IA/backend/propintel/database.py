from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .geocoder import geocode_city
from .scoring import score_process


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self):
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS procesos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_proceso TEXT NOT NULL UNIQUE,
                    juzgado TEXT,
                    ciudad TEXT NOT NULL,
                    direccion TEXT NOT NULL,
                    tipo_proceso TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    avaluo REAL DEFAULT 0,
                    edad_meses INTEGER DEFAULT 0,
                    demandados INTEGER DEFAULT 1,
                    acreedores INTEGER DEFAULT 1,
                    matricula_inmobiliaria TEXT,
                    lat REAL,
                    lng REAL,
                    geocode_precision TEXT,
                    risk_score INTEGER DEFAULT 0,
                    risk_level TEXT DEFAULT 'bajo',
                    score_factors TEXT DEFAULT '{}',
                    source TEXT DEFAULT 'manual',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS eventos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    descripcion TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS source_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    query TEXT DEFAULT '{}',
                    imported_count INTEGER DEFAULT 0,
                    message TEXT,
                    requires_human_intervention INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS watchlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    criteria TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_procesos_ciudad ON procesos(ciudad);
                CREATE INDEX IF NOT EXISTS idx_procesos_risk ON procesos(risk_level);
                CREATE INDEX IF NOT EXISTS idx_procesos_updated ON procesos(updated_at);
                CREATE INDEX IF NOT EXISTS idx_source_runs_created ON source_runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_watchlists_owner ON watchlists(owner);
                """
            )

    def upsert_process(self, payload: dict, source: str = "manual") -> dict:
        now = datetime.now(UTC).isoformat()
        data = dict(payload)
        data["source"] = source or data.get("source") or "manual"
        data["juzgado"] = data.get("juzgado") or data.get("court") or ""
        data["avaluo"] = float(data.get("avaluo") or 0)
        data["edad_meses"] = int(float(data.get("edad_meses") or 0))
        data["demandados"] = int(float(data.get("demandados") or 1))
        data["acreedores"] = int(float(data.get("acreedores") or 1))

        lat = data.get("lat")
        lng = data.get("lng")
        precision = "exact" if lat and lng else None
        if not lat or not lng:
            lat, lng, precision = geocode_city(data.get("ciudad", ""))
        data["lat"] = float(lat) if lat is not None and lat != "" else None
        data["lng"] = float(lng) if lng is not None and lng != "" else None
        data["geocode_precision"] = precision or "pending"

        scoring = score_process(data)
        data["risk_score"] = scoring["score"]
        data["risk_level"] = scoring["risk"]
        data["score_factors"] = json.dumps(scoring["factors"], ensure_ascii=False)
        data["created_at"] = now
        data["updated_at"] = now

        with self.connect() as conn:
            previous = conn.execute(
                "SELECT risk_score, estado FROM procesos WHERE numero_proceso = ?",
                (data["numero_proceso"],),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO procesos (
                    numero_proceso, juzgado, ciudad, direccion, tipo_proceso, estado,
                    avaluo, edad_meses, demandados, acreedores, matricula_inmobiliaria,
                    lat, lng, geocode_precision, risk_score, risk_level, score_factors,
                    source, created_at, updated_at
                )
                VALUES (
                    :numero_proceso, :juzgado, :ciudad, :direccion, :tipo_proceso, :estado,
                    :avaluo, :edad_meses, :demandados, :acreedores, :matricula_inmobiliaria,
                    :lat, :lng, :geocode_precision, :risk_score, :risk_level, :score_factors,
                    :source, :created_at, :updated_at
                )
                ON CONFLICT(numero_proceso) DO UPDATE SET
                    juzgado=excluded.juzgado,
                    ciudad=excluded.ciudad,
                    direccion=excluded.direccion,
                    tipo_proceso=excluded.tipo_proceso,
                    estado=excluded.estado,
                    avaluo=excluded.avaluo,
                    edad_meses=excluded.edad_meses,
                    demandados=excluded.demandados,
                    acreedores=excluded.acreedores,
                    matricula_inmobiliaria=excluded.matricula_inmobiliaria,
                    lat=excluded.lat,
                    lng=excluded.lng,
                    geocode_precision=excluded.geocode_precision,
                    risk_score=excluded.risk_score,
                    risk_level=excluded.risk_level,
                    score_factors=excluded.score_factors,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                data,
            )
            conn.execute(
                "INSERT INTO eventos(tipo, descripcion, created_at) VALUES (?, ?, ?)",
                ("upsert", f"Proceso {data['numero_proceso']} actualizado desde {data['source']}", now),
            )
            if previous and (
                int(previous["risk_score"]) != int(data["risk_score"]) or str(previous["estado"]) != str(data["estado"])
            ):
                conn.execute(
                    "INSERT INTO eventos(tipo, descripcion, created_at) VALUES (?, ?, ?)",
                    (
                        "status_change",
                        f"Cambio detectado en {data['numero_proceso']}: estado/riesgo actualizado.",
                        now,
                    ),
                )
            row = conn.execute("SELECT * FROM procesos WHERE numero_proceso = ?", (data["numero_proceso"],)).fetchone()
            return self._row(row)

    def bulk_upsert(self, records: list[dict], source: str) -> list[dict]:
        return [self.upsert_process(record, source=source) for record in records]

    def list_processes(
        self,
        city: str | None = None,
        risk: str | None = None,
        status: str | None = None,
        process_type: str | None = None,
        text: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        query = "SELECT * FROM procesos WHERE 1=1"
        params = []
        if city:
            query += " AND lower(ciudad) = lower(?)"
            params.append(city)
        if risk:
            query += " AND risk_level = ?"
            params.append(risk)
        if status:
            query += " AND lower(estado) LIKE lower(?)"
            params.append(f"%{status}%")
        if process_type:
            query += " AND lower(tipo_proceso) LIKE lower(?)"
            params.append(f"%{process_type}%")
        if text:
            query += " AND (lower(numero_proceso) LIKE lower(?) OR lower(juzgado) LIKE lower(?) OR lower(direccion) LIKE lower(?))"
            params.extend([f"%{text}%", f"%{text}%", f"%{text}%"])
        query += " ORDER BY risk_score DESC, updated_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, min(limit, 1000)), max(0, offset)])

        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row(row) for row in rows]

    def count_processes(
        self,
        city: str | None = None,
        risk: str | None = None,
        status: str | None = None,
        process_type: str | None = None,
        text: str | None = None,
    ) -> int:
        query = "SELECT COUNT(*) AS total FROM procesos WHERE 1=1"
        params = []
        if city:
            query += " AND lower(ciudad) = lower(?)"
            params.append(city)
        if risk:
            query += " AND risk_level = ?"
            params.append(risk)
        if status:
            query += " AND lower(estado) LIKE lower(?)"
            params.append(f"%{status}%")
        if process_type:
            query += " AND lower(tipo_proceso) LIKE lower(?)"
            params.append(f"%{process_type}%")
        if text:
            query += " AND (lower(numero_proceso) LIKE lower(?) OR lower(juzgado) LIKE lower(?) OR lower(direccion) LIKE lower(?))"
            params.extend([f"%{text}%", f"%{text}%", f"%{text}%"])
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row["total"] if row else 0)

    def get_process_by_number(self, numero_proceso: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM procesos WHERE numero_proceso = ?", (numero_proceso,)).fetchone()
        return self._row(row) if row else None

    def list_opportunities(self, min_score: int = 70, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM procesos
                WHERE risk_score >= ?
                ORDER BY risk_score DESC, updated_at DESC
                LIMIT ?
                """,
                (max(1, min(min_score, 99)), max(1, min(limit, 500))),
            ).fetchall()
        return [self._row(row) for row in rows]

    def list_alerts(self, limit: int = 300) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM procesos
                WHERE risk_score >= 42 OR lower(estado) LIKE '%embargo%' OR lower(estado) LIKE '%remate%'
                ORDER BY risk_score DESC, updated_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "numero_proceso": row["numero_proceso"],
                "ciudad": row["ciudad"],
                "tipo_proceso": row["tipo_proceso"],
                "estado": row["estado"],
                "risk_score": row["risk_score"],
                "risk_level": row["risk_level"],
                "message": self._alert_message(row),
            }
            for row in rows
        ]

    def list_events(self, limit: int = 30) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM eventos ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        return [dict(row) for row in rows]

    def record_event(self, tipo: str, descripcion: str):
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO eventos(tipo, descripcion, created_at) VALUES (?, ?, ?)",
                (tipo, descripcion, now),
            )

    def record_source_run(
        self,
        source: str,
        mode: str,
        status: str,
        query: dict | None = None,
        imported_count: int = 0,
        message: str = "",
        requires_human_intervention: bool = False,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO source_runs(
                    source, mode, status, query, imported_count, message,
                    requires_human_intervention, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    mode,
                    status,
                    json.dumps(query or {}, ensure_ascii=False),
                    int(imported_count or 0),
                    message,
                    1 if requires_human_intervention else 0,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO eventos(tipo, descripcion, created_at) VALUES (?, ?, ?)",
                ("source_run", f"{source} {mode}: {status}. {message}", now),
            )
            row = conn.execute("SELECT * FROM source_runs WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return self._source_row(row)

    def list_source_runs(self, limit: int = 25) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM source_runs ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._source_row(row) for row in rows]

    def source_status(self) -> dict:
        runs = self.list_source_runs(limit=1)
        latest = runs[0] if runs else None
        return {
            "source": "rama_judicial",
            "official_page": "https://consultaprocesos.ramajudicial.gov.co/Procesos/NumeroRadicacion",
            "latest_run": latest,
            "supports_automatic_captcha": False,
            "message": (
                "La plataforma consulta fuentes oficiales configuradas. "
                "Si aparece CAPTCHA o control interactivo, la corrida se marca como bloqueada y requiere intervencion humana."
            ),
        }

    def create_watchlist(self, name: str, owner: str, criteria: dict, active: bool = True) -> dict:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO watchlists(name, owner, criteria, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, owner, json.dumps(criteria or {}, ensure_ascii=False), 1 if active else 0, now, now),
            )
            row = conn.execute("SELECT * FROM watchlists WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return self._watchlist_row(row)

    def list_watchlists(self, owner: str | None = None) -> list[dict]:
        query = "SELECT * FROM watchlists"
        params = []
        if owner:
            query += " WHERE lower(owner) = lower(?)"
            params.append(owner)
        query += " ORDER BY updated_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._watchlist_row(row) for row in rows]

    def delete_watchlist(self, watchlist_id: int) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM watchlists WHERE id = ?", (watchlist_id,))
        return cursor.rowcount > 0

    def run_watchlist(self, watchlist_id: int, limit: int = 100) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
        if not row:
            raise ValueError("Watchlist no encontrada")
        watchlist = self._watchlist_row(row)
        criteria = watchlist["criteria"]
        matches = self.list_processes(
            city=criteria.get("city"),
            risk=criteria.get("risk"),
            status=criteria.get("status"),
            process_type=criteria.get("process_type"),
            text=criteria.get("text"),
            limit=max(1, min(limit, 300)),
            offset=0,
        )
        if criteria.get("min_score") is not None:
            min_score = int(criteria.get("min_score") or 0)
            matches = [item for item in matches if int(item.get("risk_score") or 0) >= min_score]
        return {"watchlist": watchlist, "matches": matches, "count": len(matches)}

    def analytics(self) -> dict:
        processes = self.list_processes(limit=1000, offset=0)
        total = len(processes)
        avg = round(sum(p["risk_score"] for p in processes) / total) if total else 0
        by_city = {}
        by_risk = {"alto": 0, "medio": 0, "bajo": 0}
        by_source = {}
        for item in processes:
            by_city[item["ciudad"]] = by_city.get(item["ciudad"], 0) + 1
            by_risk[item["risk_level"]] = by_risk.get(item["risk_level"], 0) + 1
            by_source[item["source"]] = by_source.get(item["source"], 0) + 1
        latest_runs = self.list_source_runs(limit=1)
        return {
            "total_processes": total,
            "geocoded_properties": len([p for p in processes if p.get("lat") and p.get("lng")]),
            "average_risk": avg,
            "critical_alerts": len([p for p in processes if p["risk_score"] >= 70]),
            "by_city": by_city,
            "by_risk": by_risk,
            "by_source": by_source,
            "latest_source_run": latest_runs[0] if latest_runs else None,
        }

    def business_projection(self, basic_clients: int, pro_clients: int, enterprise_clients: int, enterprise_ticket: int = 3000000):
        basic_revenue = max(0, int(basic_clients)) * 150000
        pro_revenue = max(0, int(pro_clients)) * 500000
        enterprise_revenue = max(0, int(enterprise_clients)) * max(1000000, int(enterprise_ticket))
        mrr = basic_revenue + pro_revenue + enterprise_revenue
        return {
            "basic_clients": max(0, int(basic_clients)),
            "pro_clients": max(0, int(pro_clients)),
            "enterprise_clients": max(0, int(enterprise_clients)),
            "enterprise_ticket": max(1000000, int(enterprise_ticket)),
            "mrr": mrr,
            "arr": mrr * 12,
            "breakdown": {
                "basic": basic_revenue,
                "pro": pro_revenue,
                "enterprise": enterprise_revenue,
            },
        }

    def _row(self, row: sqlite3.Row | None) -> dict:
        if not row:
            return {}
        data = dict(row)
        try:
            data["score_factors"] = json.loads(data.get("score_factors") or "{}")
        except json.JSONDecodeError:
            data["score_factors"] = {}
        return data

    def _source_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        try:
            data["query"] = json.loads(data.get("query") or "{}")
        except json.JSONDecodeError:
            data["query"] = {}
        data["requires_human_intervention"] = bool(data.get("requires_human_intervention"))
        return data

    def _watchlist_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        try:
            data["criteria"] = json.loads(data.get("criteria") or "{}")
        except json.JSONDecodeError:
            data["criteria"] = {}
        data["active"] = bool(data.get("active"))
        return data

    def _alert_message(self, row) -> str:
        if int(row["risk_score"]) >= 70:
            return "Prioridad alta: validar expediente, titulos, avaluo, gravamenes y fecha de remate."
        if "embargo" in str(row["estado"]).lower():
            return "Embargo detectado: monitorear actuaciones y cambios de estado."
        return "Seguimiento recomendado por madurez procesal."
