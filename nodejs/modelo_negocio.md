# Plataforma de Inteligencia Judicial Inmobiliaria Colombia

## Producto

Sistema SaaS B2B que monitorea fuentes judiciales públicas, detecta eventos inmobiliarios relevantes y entrega alertas, reportes y mapas a abogados, inmobiliarias, fondos pequeños, compradores de remates y oficinas de cobranza.

No vende representación legal. Vende datos públicos organizados, analítica, seguimiento y señales comerciales.

## Paquetes

Starter - 249.000 COP/mes
- 20 procesos monitoreados
- Alertas por email/Telegram
- Reporte semanal
- Ideal para abogados independientes

Pro - 799.000 COP/mes
- 250 procesos monitoreados
- Dashboard, filtros, exportaciones
- Alertas por remate, embargo, avalúo y pertenencia
- 3 usuarios

Enterprise - 2.500.000 a 6.000.000 COP/mes
- Monitoreo masivo por ciudad, juzgado, demandante o clase de proceso
- API privada
- Mapa GIS de inmuebles
- Scoring de oportunidad
- Soporte y reportes ejecutivos

## Camino a 20-50M COP mensuales

Escenario conservador:
- 30 clientes Starter x 249.000 = 7,47M
- 15 clientes Pro x 799.000 = 11,98M
- 3 Enterprise x 3.500.000 = 10,5M
- Total: 29,95M COP/mes

Escenario fuerte:
- 50 clientes Starter x 249.000 = 12,45M
- 25 clientes Pro x 799.000 = 19,97M
- 6 Enterprise x 4.000.000 = 24M
- Total: 56,42M COP/mes

## Diferenciadores

1. Monitoreo recurrente, no consulta manual.
2. Detección de cambios y trazabilidad histórica.
3. Señales inmobiliarias: embargo, secuestro, avalúo, remate, pertenencia.
4. Georreferenciación con PostGIS.
5. Scoring predictivo entrenado con historial de eventos y desenlaces.

## Go-to-market

Fase 1: vender alertas a abogados litigantes e inmobiliarias de Bogotá, Medellín, Cali, Barranquilla y Bucaramanga.

Fase 2: vender dashboard Pro a firmas que ya compran información judicial manualmente.

Fase 3: vender API/datos a fondos, originadores hipotecarios, oficinas de cobranza y compradores profesionales de remates.

## Costos esperados

- Infraestructura inicial: 300k-1,2M COP/mes.
- Mensajería/email: 100k-500k COP/mes.
- Geocodificación/GIS: 0-1M COP/mes según volumen.
- Operación y soporte: 1 persona parcial al inicio.
- Legal/contratos/privacidad: presupuesto obligatorio antes de vender masivamente.

## Riesgos y controles

- Carga excesiva a fuentes públicas: usar colas, rate limits, horarios, cache y semillas justificadas.
- Datos personales: minimización, finalidad legítima, retención limitada y control de acceso.
- Error de interpretación jurídica: mostrar evidencia fuente y evitar conclusiones legales categóricas.
- Cambios en la web fuente: pruebas diarias, monitoreo de selectores y fallback manual.

## Arquitectura comercial defensible

El activo vendible no es solo el scraper. Es la operación confiable:

- Colas transaccionales para procesar miles de radicados sin desorden.
- Rate limits por fuente para sostener el negocio sin abusar de datos públicos.
- Cache para bajar costos y reducir consultas repetidas.
- Auditoría para clientes enterprise y defensa contractual.
- Backlog legal de tratamiento de datos para demostrar responsabilidad.

Esto permite cobrar más a clientes profesionales porque compran tranquilidad operativa, no solo alertas.

Nuevo paquete Compliance Enterprise - desde 6M COP/mes:
- Auditoría mensual de consultas.
- Reporte de fuentes, eventos, cache y errores.
- Retención personalizada.
- API con límites de uso.
- Contrato de encargado/responsable revisado por abogado.

## Roadmap técnico

MVP 30 días:
- Scraper por radicado
- Base PostgreSQL
- Detección de cambios
- Alertas Telegram/email
- Dashboard básico

Versión 60-90 días:
- Watchlists por cliente
- Mapa PostGIS
- Enriquecimiento de inmuebles
- Exportación CSV/PDF

Versión 120-180 días:
- Modelo predictivo
- API comercial
- Multiusuario con roles
- Auditoría y facturación recurrente
