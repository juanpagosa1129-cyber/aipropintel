# Operacion del sistema

## 1. Instalar dependencias

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## 2. Configurar base

```powershell
$env:DATABASE_URL="postgresql://user:pass@localhost:5432/judicial_ai"
python judicial_pipeline.py init-db
```

## 3. Encolar procesos

Agrega radicados a `seeds.txt` y ejecuta:

```powershell
python judicial_pipeline.py enqueue --seeds seeds.txt
```

## 4. Ejecutar worker

```powershell
python judicial_pipeline.py worker --headless --max-jobs 100 --exit-when-empty
```

Para operacion continua:

```powershell
python judicial_pipeline.py worker --headless
```

## 5. Alertas Telegram opcionales

```powershell
$env:TELEGRAM_BOT_TOKEN="token"
$env:TELEGRAM_CHAT_ID="chat_id"
```

## 6. Consultas utiles

Trabajos pendientes:

```sql
select status, count(*)
from crawl_jobs
group by status;
```

Eventos recientes:

```sql
select process_id, event_type, severity, created_at
from process_events
order by created_at desc
limit 50;
```

Auditoria:

```sql
select actor, action, entity_type, entity_id, created_at
from audit_log
order by created_at desc
limit 100;
```

Revision legal abierta:

```sql
select severity, title, due_at
from privacy_review_items
where status <> 'closed'
order by due_at asc;
```

## 7. Metricas que debes mirar cada dia

- `cache_hit / cache_miss`
- trabajos `dead`
- errores por cambio de selector
- consultas consumidas por fuente
- eventos de alta severidad
- solicitudes de titulares abiertas

## 8. Regla de oro

Si necesitas mas volumen, agrega workers y mejora colas, pero conserva el rate limit centralizado. La fuente publica nunca debe ser tratada como infraestructura propia.
