# PropIntel Judicial

App web SaaS para monitoreo judicial inmobiliario en Colombia.

Incluye:

- Backend Express
- Frontend React/Vite
- MySQL
- Autenticacion JWT
- Dashboard
- Cola de trabajos
- Worker
- Cache
- Rate limit
- Auditoria
- Cumplimiento de datos
- Guia de despliegue Hostinger

## Desarrollo local

```powershell
npm install
copy .env.example .env
npm run db:init
npm run dev
```

En otra terminal:

```powershell
npm run server
```

Con MySQL local por Docker:

```powershell
docker compose up -d
$env:DB_HOST="127.0.0.1"
$env:DB_PORT="3306"
$env:DB_USER="propintel"
$env:DB_PASSWORD="propintel_pass"
$env:DB_NAME="propintel"
npm run db:init
npm run build
npm start
```

Para produccion:

```powershell
npm install
npm run build
npm start
```

## Modo fuente

- `SOURCE_MODE=demo`: operacion completa sin depender de terceros.
- `SOURCE_MODE=cpnu`: conector responsable a CPNU sin evasion de controles.

## Despliegue

Lee [HOSTINGER_DEPLOY.md](C:/Users/juanm/Documents/Codex/2026-05-05/te-voy-a-mostrar-un-proyecto/HOSTINGER_DEPLOY.md).
