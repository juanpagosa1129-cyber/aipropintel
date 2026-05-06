# Arquitectura Propintel IA

## Flujo operativo

```text
Fuentes publicas autorizadas / CSV / expedientes propios
  -> Adaptadores de ingestion
  -> Normalizador
  -> SQLite o PostgreSQL
  -> Motor de scoring
  -> Alertas
  -> API REST
  -> Frontend PWA
```

## Backend

El backend esta implementado con libreria estandar de Python para reducir friccion de despliegue. Expone HTTP REST, sirve el frontend y persiste en SQLite.

Para produccion de alto volumen, reemplazar:

- `sqlite3` por PostgreSQL + PostGIS.
- `ThreadingHTTPServer` por FastAPI/Uvicorn o Gunicorn.
- Jobs manuales por Celery/RQ/Temporal.
- Scoring deterministico por modelo entrenado con historicos.

## Seguridad y cumplimiento

- No evade CAPTCHAs ni barreras de acceso.
- No automatiza sitios sin endpoint autorizado.
- Mantiene eventos de actualizacion.
- El scoring es priorizacion, no recomendacion juridica final.
