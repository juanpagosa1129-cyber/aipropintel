# Cumplimiento y gobierno de datos

Este documento es una guia operativa. Antes de vender masivamente, revisalo con abogado colombiano experto en datos personales, derecho procesal y contratos B2B.

## Base normativa minima

- Ley 1581 de 2012: regimen general de proteccion de datos personales en Colombia.
- Decreto 1377 de 2013 y Decreto Unico 1074 de 2015: reglas de autorizacion, politicas, deberes y responsabilidad demostrada.
- SIC / RNBD: revisar si la empresa debe inscribir sus bases de datos y mantenerlas actualizadas.

## Principios de producto

1. Finalidad especifica: monitoreo judicial inmobiliario con datos publicos para clientes profesionales.
2. Minimizacion: guardar solo lo necesario para detectar cambios, probar fuente y emitir alertas.
3. Circulacion restringida: dashboard con usuarios autenticados, roles, logs y limites contractuales.
4. Calidad: mostrar fecha de captura, fuente, hash y enlace oficial cuando exista.
5. Transparencia: politica de tratamiento visible y canal de consultas/reclamos.
6. Seguridad: cifrado en transito, backups protegidos, claves fuera del codigo y control de acceso.
7. Retencion: borrar o anonimizar datos cuando ya no sirvan a la finalidad aprobada.

## Controles tecnicos implementados

- Cola `crawl_jobs`: evita scraping desordenado y permite trazabilidad por trabajo.
- `source_rate_limits`: controla intervalo minimo y cuota diaria por fuente.
- `crawl_cache`: evita consultar la misma fuente cuando el dato sigue fresco.
- `audit_log`: registra encolado, cache hit/miss, consumo de cuota, snapshots y eventos.
- `privacy_review_items`: backlog de revisiones obligatorias de privacidad.
- `data_subject_requests`: registro de solicitudes de acceso, correccion, supresion, oposicion o reclamo.

## Politica de retencion sugerida

- Cache HTML: 12 a 24 horas.
- Snapshots: 12 a 24 meses si hay contrato activo y finalidad vigente.
- Alertas: 24 meses para trazabilidad comercial.
- Auditoria: 36 meses.
- Leads no convertidos: 90 dias.

Estas ventanas son una propuesta de negocio, no una conclusion legal. Deben aprobarse formalmente.

## Flujo de revision legal antes de produccion

1. Identificar responsable y encargado del tratamiento.
2. Redactar politica de tratamiento de datos.
3. Crear canal de habeas data y SLA de respuesta.
4. Definir bases de datos y evaluar RNBD ante la SIC.
5. Clasificar datos: publicos, personales, sensibles, menores, reservados.
6. Prohibir ingestion de datos reservados o acceso no autorizado.
7. Firmar contratos con clientes con limites de uso y no asesoria juridica.
8. Aprobar matriz de riesgos y tabla de retencion.
9. Hacer prueba de carga responsable contra cada fuente.
10. Activar monitoreo de errores, cuota, cambios de selectores y auditoria.

## Reglas comerciales para clientes

- El sistema entrega informacion publica organizada y analitica comercial.
- La plataforma no sustituye revision juridica ni representa a partes.
- El cliente debe verificar cada decision de inversion con fuente oficial y asesoria profesional.
- Se prohibe usar datos para acoso, discriminacion, fraude, extorsion o finalidades incompatibles.
- Se prohibe revender bases completas salvo contrato enterprise especifico.

## Checklist de lanzamiento

- [ ] Politica de tratamiento publicada.
- [ ] Terminos de servicio firmados.
- [ ] Contrato de encargado/responsable revisado.
- [ ] Canal de solicitudes de titulares activo.
- [ ] RNBD evaluado.
- [ ] Roles y permisos probados.
- [ ] Backups cifrados.
- [ ] Variables secretas fuera del repositorio.
- [ ] Rate limits activos por fuente.
- [ ] Auditoria consultable.
- [ ] Procedimiento de incidente documentado.
