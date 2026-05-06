# Fuentes publicas y datos

Propintel IA puede operar con:

- Exportaciones CSV de expedientes propios.
- Datos abiertos territoriales.
- Capas catastrales autorizadas.
- Endpoints publicos que permitan consulta automatizada.
- Proveedores privados con licencia.

## Rama Judicial

El adaptador `RamaJudicialSource` requiere configurar `RAMA_JUDICIAL_BASE_URL`.

Debe apuntar a un endpoint permitido que devuelva JSON con `items` o una lista de registros normalizados. La plataforma no intenta saltar controles de acceso, CAPTCHAs o restricciones tecnicas.

## Campos minimos

- `numero_proceso`
- `ciudad`
- `direccion`
- `tipo_proceso`
- `estado`

Campos recomendados:

- `juzgado`
- `avaluo`
- `edad_meses`
- `demandados`
- `acreedores`
- `matricula_inmobiliaria`
- `lat`
- `lng`
