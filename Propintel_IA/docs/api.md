# API REST - Propintel IA

## Salud

- `GET /api/health`

## Procesos

- `GET /api/processes`
  - filtros: `city`, `risk`, `status`, `type`, `q`, `limit`, `offset`
- `GET /api/processes/detail?numero_proceso=...`
- `POST /api/processes`

## Importacion

- `POST /api/import/csv`
  - body JSON:
```json
{
  "csv_text": "numero_proceso,juzgado,ciudad,direccion,tipo_proceso,estado\n..."
}
```

## Fuente oficial y crawler

- `POST /api/live/search`
- `POST /api/crawler/run`
- `GET /api/source/status`
- `GET /api/source/runs`

## Bot diario

- `GET /api/bot/config`
- `POST /api/bot/config`
- `POST /api/bot/run-now`

## Alertas y analitica

- `GET /api/alerts`
- `GET /api/events`
- `GET /api/analytics`
- `GET /api/opportunities`

## Watchlists

- `GET /api/watchlists`
- `POST /api/watchlists`
- `POST /api/watchlists/run`
- `POST /api/watchlists/delete`

## Negocio

- `GET /api/business/projection`
  - query: `basic`, `pro`, `enterprise`, `enterprise_ticket`

## Tiempo real

- `GET /api/stream/events`
  - stream `text/event-stream` con evento `state`.
