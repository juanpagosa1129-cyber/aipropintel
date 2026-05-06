# Diagnostico Hostinger 503

Un `503 Service Unavailable` despues de que el build paso casi siempre significa que el proceso Node no arranco o se cayo durante el inicio.

## 1. Verifica la URL de salud

Abre:

```text
https://aipropintel.geeks4u.digital/api/health
```

Respuesta correcta:

```json
{
  "ok": true,
  "dbReady": true,
  "sourceMode": "demo",
  "startupError": null
}
```

Si responde `startupError`, el problema ya no es generico: normalmente es MySQL.

## 2. Configuracion obligatoria de Hostinger

En la app Node:

```text
Root directory: ./
Build command: npm install && npm run build
Start command: npm start
Entry file: server/index.js
Node version: 20.x
```

## 3. Variables de entorno obligatorias

```env
NODE_ENV=production
DB_HOST=host_mysql_de_hostinger
DB_PORT=3306
DB_USER=usuario_mysql
DB_PASSWORD=clave_mysql
DB_NAME=nombre_base_mysql
JWT_SECRET=secreto_largo
ADMIN_EMAIL=tu_email
ADMIN_PASSWORD=clave_segura
CRON_SECRET=secreto_cron
SOURCE_MODE=demo
WORKER_ENABLED=true
WORKER_INTERVAL_SECONDS=60
CACHE_TTL_HOURS=12
SOURCE_MIN_SECONDS=8
SOURCE_DAILY_LIMIT=1500
```

## 4. Errores comunes

- `Access denied for user`: usuario o clave MySQL incorrectos.
- `Unknown database`: `DB_NAME` no coincide con la base creada.
- `getaddrinfo ENOTFOUND`: `DB_HOST` incorrecto.
- `ECONNREFUSED`: host/puerto incorrecto o MySQL no accesible desde la app.
- `Cannot find module`: no se subio todo el proyecto o el build/start usa otra carpeta.

## 5. Si sigue 503

Abre los runtime logs de Hostinger, no solo build logs. Busca lineas despues de:

```text
npm start
node server/index.js
```

Copia el primer error real que aparezca.
