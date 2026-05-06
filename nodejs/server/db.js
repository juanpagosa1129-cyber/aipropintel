import fs from 'node:fs/promises';
import path from 'node:path';
import bcrypt from 'bcryptjs';
import mysql from 'mysql2/promise';

const rootDir = process.cwd();

export const pool = mysql.createPool({
  host: process.env.DB_HOST || process.env.MYSQL_HOST || 'localhost',
  port: Number(process.env.DB_PORT || process.env.MYSQL_PORT || 3306),
  user: process.env.DB_USER || process.env.MYSQL_USER || 'root',
  password: process.env.DB_PASSWORD || process.env.MYSQL_PASSWORD || '',
  database: process.env.DB_NAME || process.env.MYSQL_DATABASE || 'propintel',
  waitForConnections: true,
  connectionLimit: Number(process.env.DB_POOL_SIZE || 10),
  multipleStatements: true,
  namedPlaceholders: true
});

export async function query(sql, params = []) {
  const [rows] = await pool.execute(sql, params);
  return rows;
}

export async function one(sql, params = []) {
  const rows = await query(sql, params);
  return rows[0] || null;
}

export async function withConnection(fn) {
  const conn = await pool.getConnection();
  try {
    return await fn(conn);
  } finally {
    conn.release();
  }
}

export async function initSchema() {
  const schemaPath = path.join(rootDir, 'database', 'schema.mysql.sql');
  const schema = await fs.readFile(schemaPath, 'utf8');
  await pool.query(schema);
  await ensureDefaults();
}

async function ensureDefaults() {
  const sourceMin = Number(process.env.SOURCE_MIN_SECONDS || 8);
  const dailyLimit = Number(process.env.SOURCE_DAILY_LIMIT || 1500);
  await query(
    `insert into source_rate_limits
      (source_key, min_seconds_between_requests, daily_limit, day, requests_today)
     values ('rama_judicial_cpnu', ?, ?, current_date(), 0)
     on duplicate key update
      min_seconds_between_requests = values(min_seconds_between_requests),
      daily_limit = values(daily_limit)`,
    [sourceMin, dailyLimit]
  );

  const adminEmail = process.env.ADMIN_EMAIL || 'admin@propintel.co';
  const adminPassword = process.env.ADMIN_PASSWORD || 'CambiaEstaClave2026!';
  const existingAdmin = await one('select id from users where email = ?', [adminEmail]);
  if (!existingAdmin) {
    const passwordHash = await bcrypt.hash(adminPassword, 12);
    await query(
      `insert into users (email, password_hash, role, name)
       values (?, ?, 'admin', 'Administrador')`,
      [adminEmail, passwordHash]
    );
  }

  const reviewItems = [
    ['policy', 'Politica de tratamiento de datos', 'Publicar finalidad, responsable, derechos del titular, canales y retencion.', 'critical'],
    ['rn_bases_datos', 'Evaluar RNBD ante la SIC', 'Confirmar si la empresa debe inscribir bases de datos y mantenerlas actualizadas.', 'high'],
    ['contracts', 'Contratos B2B y limites de uso', 'Prohibir reventa no autorizada, asesoría jurídica automatica y usos incompatibles.', 'high'],
    ['security', 'Controles de acceso y secretos', 'Validar roles, backups, JWT_SECRET fuerte y credenciales fuera del repositorio.', 'high']
  ];
  for (const item of reviewItems) {
    const exists = await one('select id from privacy_review_items where item_type = ? and title = ?', [item[0], item[1]]);
    if (!exists) {
      await query(
        `insert into privacy_review_items (item_type, title, description, severity, due_at, metadata)
         values (?, ?, ?, ?, date_add(now(), interval 14 day), json_object())`,
        item
      );
    }
  }

  const demoClient = await one('select id from clients where email = ?', ['operaciones@propintel.co']);
  if (!demoClient) {
    await query(
      `insert into clients (name, email, plan, monthly_price_cop)
       values ('PropIntel Operaciones', 'operaciones@propintel.co', 'enterprise', 3500000)`
    );
  }
}

export async function audit({
  actor = 'system',
  action,
  entityType,
  entityId = null,
  metadata = {},
  lawfulBasis = 'public_judicial_information',
  purpose = 'real_estate_judicial_monitoring'
}) {
  await query(
    `insert into audit_log
      (actor, action, entity_type, entity_id, lawful_basis, purpose, metadata)
     values (?, ?, ?, ?, ?, ?, ?)`,
    [actor, action, entityType, entityId, lawfulBasis, purpose, JSON.stringify(metadata)]
  );
}
