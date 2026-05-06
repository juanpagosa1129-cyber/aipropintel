import 'dotenv/config';
import { initSchema, pool } from './db.js';

try {
  await initSchema();
  console.log('Base MySQL inicializada correctamente');
} finally {
  await pool.end();
}
