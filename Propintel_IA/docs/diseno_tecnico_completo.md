# Diseno Tecnico Completo - Propintel IA

## 1. Objetivo de producto

Construir una plataforma de Inteligencia Judicial Inmobiliaria para Colombia que:

- monitoree procesos judiciales inmobiliarios de forma continua,
- consolide datos en una base trazable,
- georreferencie inmuebles en litigio,
- calcule alertas y probabilidad de remate,
- entregue panel profesional para abogados, inversionistas, inmobiliarias y fondos.

## 2. Crawler masivo de procesos judiciales

### 2.1 Arquitectura operacional

```text
Job Scheduler
  -> Generador de combinaciones de consulta
  -> Cola de trabajo (Redis/Kafka)
  -> Workers distribuidos (crawler adapters)
  -> Parser y normalizador
  -> Motor de calidad de datos
  -> PostgreSQL + PostGIS
  -> Motor de eventos y alertas
  -> API + Dashboard + Webhooks
```

### 2.2 Componentes clave

1. `Scheduler`: ejecuta lotes por ventana horaria (ej. cada 30 min).
2. `Generator`: crea combinaciones por ciudad, tipo de proceso, rango temporal y radicacion.
3. `Workers`: consumen tareas en paralelo y registran metricas de exito/fallo.
4. `Source adapters`: un adaptador por fuente oficial autorizada.
5. `Parser`: convierte respuesta cruda a esquema canonico.
6. `Dedup`: upsert por `numero_proceso` + hash de actuacion.
7. `Event engine`: detecta cambios de estado y dispara alertas.

### 2.3 Regla de cumplimiento

- No evadir CAPTCHA ni controles interactivos.
- Si la fuente bloquea la consulta, registrar `blocked_interactive` y escalar a intervencion humana.
- Mantener historial de corridas (`source_runs`) con estado, mensaje y query.

### 2.4 Estrategia de consulta masiva

- Particionar por ciudad y tipo de proceso.
- Priorizar procesos activos y con senales de madurez.
- Guardar `cursor/page` por corrida para reintentos idempotentes.
- Aplicar `backoff` y circuit breaker ante errores repetidos.

## 3. GIS de inmuebles en litigio

### 3.1 Flujo de datos GIS

```text
Proceso judicial
  -> Extraccion de direccion/matricula
  -> Geocodificacion
  -> Validacion de precision (exacta/aproximada/pendiente)
  -> Capa PostGIS
  -> API de mapas
  -> Vista interactiva Colombia
```

### 3.2 Modelo espacial base

```sql
CREATE TABLE inmuebles_litigio (
  id BIGSERIAL PRIMARY KEY,
  numero_proceso TEXT NOT NULL,
  matricula_inmobiliaria TEXT,
  direccion TEXT NOT NULL,
  ciudad TEXT NOT NULL,
  geom GEOGRAPHY(POINT, 4326),
  geocode_precision TEXT NOT NULL,
  tipo_proceso TEXT NOT NULL,
  estado TEXT NOT NULL,
  risk_score INT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_inmuebles_geom ON inmuebles_litigio USING GIST (geom);
```

### 3.3 Vista GIS para decision

- Cluster por zoom.
- Filtros por ciudad, tipo, riesgo, estado y rango de fechas.
- Ficha lateral con datos legales y riesgo.
- Heatmap de zonas con mayor concentracion de procesos.

## 4. Modelo de IA para prediccion de remate

### 4.1 Definicion del problema

- Objetivo: `P(remate <= N meses)`.
- Tipo: clasificacion supervisada binaria y luego multicategoria (`remate/acuerdo/archivo`).

### 4.2 Features recomendadas

- tipo_proceso (one-hot),
- edad_meses,
- estado_actual,
- numero_actuaciones_ultimos_90d,
- avaluo_aprobado,
- embargo,
- numero_demandados,
- numero_acreedores,
- ciudad y congestion judicial aproximada,
- tiempo desde ultima actuacion.

### 4.3 Pipeline ML

1. Curacion de historico etiquetado.
2. Split temporal (no aleatorio puro) para evitar leakage.
3. Baseline: Logistic Regression.
4. Modelo productivo inicial: Random Forest o XGBoost.
5. Calibracion de probabilidades (Platt/Isotonic).
6. Explicabilidad por feature importance y SHAP.
7. Reentrenamiento mensual o por drift.

### 4.4 Metrica objetivo

- AUC-ROC >= 0.78,
- Precision@TopK para ranking de oportunidades,
- Brier score para calibracion.

## 5. Arquitectura empresarial escalable

### 5.1 Servicios

- `ingestion-service` (crawlers y adapters),
- `normalization-service`,
- `risk-service` (scoring y ML inference),
- `alerts-service`,
- `api-gateway` (FastAPI),
- `web-app` (frontend),
- `ops-monitoring` (logs, tracing, metricas).

### 5.2 Stack recomendado

- Backend: Python + FastAPI.
- Cola: Redis Streams o Kafka.
- Datos: PostgreSQL + PostGIS.
- Cache: Redis.
- Jobs: Celery/RQ/Temporal.
- Frontend: React/Next.js.
- Infra: Docker + AWS (ECS/RDS/S3/CloudWatch) o DigitalOcean.

### 5.3 Tiempo real

- API REST para consulta.
- SSE/WebSocket para eventos de nuevas alertas.
- Actualizacion incremental del dashboard cada 10-30s.

## 6. Seguridad y gobierno de datos

- RBAC por perfil (analista, abogado, admin, API client).
- Auditoria de consultas y exportaciones.
- Cifrado en reposo y en transito.
- Politica de retencion y anonimizado para reportes agregados.
- Registro explicito de fuentes y terminos de uso.

## 7. Modelo de negocio

### 7.1 Planes

1. Basico (`150k COP/mes`): alertas y seguimiento simple.
2. Profesional (`500k COP/mes`): mapa GIS + exportacion avanzada + filtros.
3. Empresarial (`2M-5M COP/mes`): API, integraciones, scoring predictivo y SLA.

### 7.2 Unit economics inicial

- 100 clientes con ticket promedio `300k COP`:
- MRR estimado: `30M COP`.
- Upsell por API + automatizacion + reportes legales premium.

## 8. Roadmap de implementacion

1. Fase 1 (2-4 semanas): ingestion oficial + panel operativo + alertas basicas.
2. Fase 2 (4-8 semanas): PostGIS, capas GIS y filtros avanzados.
3. Fase 3 (6-10 semanas): modelo ML v1 + explicabilidad + ranking.
4. Fase 4 (8-12 semanas): multi-tenant, facturacion y API comercial.
5. Fase 5 (continuo): optimizacion de recall, costo y cobertura.

## 9. KPIs de exito

- Cobertura de procesos monitoreados por ciudad.
- Latencia de deteccion de cambio de estado.
- Precision de alertas relevantes.
- Conversion de consulta a accion comercial.
- Retencion mensual por segmento.
