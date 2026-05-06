# Despliegue en Hostinger Cloud Startup

Stack elegido para este plan:

- Node.js 20+
- Express para API y servidor web
- React/Vite para frontend
- MySQL gestionado de Hostinger
- Un solo servicio Node que sirve `/api/*` y `dist/`

## 1. Crear base MySQL

En hPanel:

1. Entra a `Databases`.
2. Crea una base MySQL.
3. Guarda host, puerto, nombre de base, usuario y clave.

## 2. Subir el proyecto

Opciones:

- Git: conecta el repositorio y define build/start.
- File Manager/FTP: sube todo el proyecto excepto `node_modules`.

## 3. Configurar Node.js App

En hPanel:

- Runtime: Node.js 20 o superior.
- Build command: `npm install && npm run build`
- Start command: `npm start`
- App root: carpeta raiz del proyecto.
- Public path: lo sirve Express desde `dist`, no necesitas exponer `src`.

## 4. Variables de entorno

Usa `.env.example` como plantilla:

```env
NODE_ENV=production
PORT=3000
DB_HOST=host-de-mysql
DB_PORT=3306
DB_USER=usuario
DB_PASSWORD=clave
DB_NAME=base
JWT_SECRET=secreto-largo
ADMIN_EMAIL=admin@tudominio.com
ADMIN_PASSWORD=clave-segura
CRON_SECRET=otro-secreto
WORKER_ENABLED=true
WORKER_INTERVAL_SECONDS=60
SOURCE_MODE=demo
CACHE_TTL_HOURS=12
SOURCE_MIN_SECONDS=8
SOURCE_DAILY_LIMIT=1500
```

Para pilotos comerciales usa `SOURCE_MODE=demo`. Para pruebas con fuente viva usa `SOURCE_MODE=cpnu`; ese modo no evade controles de acceso ni captchas.

## 5. Inicializar base

Si Hostinger permite consola:

```bash
npm run db:init
```

Si no, la app ejecuta la inicializacion al arrancar con `npm start`.

## 6. Primer ingreso

URL:

```text
https://tudominio.com
```

Credenciales iniciales:

- Email: valor de `ADMIN_EMAIL`
- Clave: valor de `ADMIN_PASSWORD`

Cambia esas credenciales antes de vender.

## 7. Worker y cron

Opcion A: worker interno:

```env
WORKER_ENABLED=true
WORKER_INTERVAL_SECONDS=60
```

Opcion B: cron externo de Hostinger:

```text
https://tudominio.com/api/cron/tick?secret=CRON_SECRET
```

Ejecutalo cada 1 a 5 minutos. El rate limit centralizado evita exceder la cuota de fuente.

## 8. Verificacion

1. Entra al dashboard.
2. Ve a `Cola`.
3. Pulsa `Demo`.
4. Pulsa `Worker`.
5. Revisa `Monitoreo`, `Alertas`, `Auditoria` y `Cumplimiento`.

## 9. Antes de vender

- Publica politica de tratamiento de datos.
- Evalua RNBD con abogado.
- Cambia `JWT_SECRET`, `ADMIN_PASSWORD` y `CRON_SECRET`.
- Configura backups de MySQL.
- Define contratos B2B con limites de uso.
- Mantén `SOURCE_MIN_SECONDS` y `SOURCE_DAILY_LIMIT` conservadores.
