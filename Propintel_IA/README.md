# Propintel IA

Plataforma de inteligencia judicial inmobiliaria para Colombia: monitoreo de procesos, inventario de inmuebles en litigio, alertas, mapa GIS operativo y scoring de probabilidad de remate.

Esta entrega es una aplicacion funcional local-first con backend real, base SQLite persistente y frontend PWA. No usa datos ficticios por defecto: se alimenta con carga manual o CSV de fuentes publicas/propias. Los conectores externos quedan como adaptadores configurables para operar respetando terminos de uso, disponibilidad publica y controles de acceso de cada fuente.

## Estructura

```text
Propintel_IA/
  backend/
    app.py
    propintel/
      config.py
      database.py
      geocoder.py
      scoring.py
      sources/
        csv_source.py
        rama_judicial.py
  frontend/
    index.html
    styles.css
    app.js
    manifest.json
    sw.js
  scripts/
    run.ps1
    import_csv.ps1
  data/
    propintel.sqlite3
    sample_import.csv
  docs/
    arquitectura.md
    fuentes_publicas.md
    diseno_tecnico_completo.md
  tests/
    test_scoring.py
```

## Ejecutar

Desde esta carpeta:

```powershell
.\scripts\run.ps1
```

O manualmente:

```powershell
python backend\app.py
```

Abrir:

[http://127.0.0.1:8088](http://127.0.0.1:8088)

## Importar datos reales

El backend acepta CSV con estas columnas:

```text
numero_proceso,juzgado,ciudad,direccion,tipo_proceso,estado,avaluo,edad_meses,demandados,acreedores,matricula_inmobiliaria,lat,lng
```

Ejemplo:

```powershell
.\scripts\import_csv.ps1 .\data\sample_import.csv
```

## API principal

- `GET /api/health`
- `GET /api/processes`
- `GET /api/processes/detail`
- `POST /api/processes`
- `POST /api/import/csv`
- `GET /api/opportunities`
- `GET /api/alerts`
- `GET /api/analytics`
- `GET /api/events`
- `POST /api/crawler/run`
- `POST /api/live/search`
- `GET /api/source/status`
- `GET /api/source/runs`
- `GET /api/bot/config`
- `POST /api/bot/config`
- `POST /api/bot/run-now`
- `GET /api/watchlists`
- `POST /api/watchlists`
- `POST /api/watchlists/run`
- `POST /api/watchlists/delete`
- `GET /api/business/projection`
- `GET /api/stream/events`

## Produccion

Para uso real empresarial:

1. Migrar SQLite a PostgreSQL + PostGIS.
2. Configurar fuentes autorizadas y limites de consulta.
3. Activar jobs programados con `POST /api/crawler/run`.
4. Agregar autenticacion, roles y auditoria.
5. Entrenar el modelo con historicos propios verificados.

El scoring incluido es deterministico y explicable; esta listo para operar como motor inicial de priorizacion, no como decision juridica automatica.
