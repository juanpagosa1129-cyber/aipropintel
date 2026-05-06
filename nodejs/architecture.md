# Arquitectura productiva

## Vista general

```mermaid
flowchart TD
  A["Clientes / watchlists"] --> B["crawl_jobs"]
  B --> C["Workers Playwright"]
  C --> D["source_rate_limits"]
  C --> E["crawl_cache"]
  C --> F["CPNU Rama Judicial"]
  E --> G["Parser y normalizacion"]
  F --> G
  G --> H["monitored_processes"]
  G --> I["process_snapshots"]
  H --> J["Motor de eventos"]
  J --> K["process_events"]
  K --> L["Alertas"]
  G --> M["audit_log"]
  N["privacy_review_items"] --> O["Revision legal"]
  P["data_subject_requests"] --> O
```

## Componentes

- Cola: `crawl_jobs`, con `queued`, `leased`, `done`, `dead`, reintentos y `run_after`.
- Workers: procesos independientes que toman trabajos con `for update skip locked`.
- Rate limit: `source_rate_limits` define intervalo minimo y cuota diaria por fuente.
- Cache: `crawl_cache` evita volver a consultar radicados dentro del TTL.
- Auditoria: `audit_log` deja prueba de acciones y finalidad declarada.
- Cumplimiento: `privacy_review_items` y `data_subject_requests` convierten la privacidad en flujo operativo.

## Comandos

```powershell
$env:DATABASE_URL="postgresql://user:pass@localhost:5432/judicial_ai"
python judicial_pipeline.py init-db
python judicial_pipeline.py enqueue --seeds seeds.txt
python judicial_pipeline.py worker --headless --max-jobs 100 --exit-when-empty
```

## Escalamiento

Para subir volumen, aumenta workers, no velocidad contra la fuente. El cuello de botella se controla con `source_rate_limits`, asi que varios workers comparten la misma cuota y no pisan la fuente publica.

Configuracion conservadora inicial:

- 1 worker
- 8 a 15 segundos entre solicitudes
- 500 a 2.000 consultas diarias
- cache 12 horas

Configuracion enterprise responsable:

- 3 a 10 workers
- cuota por fuente centralizada
- colas por prioridad
- ventana nocturna para backfill
- observabilidad: trabajos por estado, errores por selector, cache hit rate y alertas por cambio de HTML
