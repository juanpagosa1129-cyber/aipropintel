import 'dotenv/config';
import path from 'node:path';
import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import { fileURLToPath } from 'node:url';
import { initSchema, one, pool, query } from './db.js';
import { requireAdmin, requireAuth, signToken, verifyLogin } from './auth.js';
import { enqueueRadicado, processOneJob, startWorkerLoop, upsertSnapshot } from './worker.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const app = express();
const port = Number(process.env.PORT || 3000);
let dbReady = false;
let startupError = null;

app.set('trust proxy', 1);
app.use(helmet({ contentSecurityPolicy: false }));
app.use(cors());
app.use(express.json({ limit: '1mb' }));
app.use(rateLimit({ windowMs: 60_000, max: 240 }));

initSchema()
  .then(() => {
    dbReady = true;
    startupError = null;
    console.log('Base MySQL inicializada');
  })
  .catch((error) => {
    dbReady = false;
    startupError = error;
    console.error('No se pudo inicializar MySQL:', error.message);
  });

app.get('/api/health', async (_req, res) => {
  try {
    const db = await one('select 1 as ok');
    dbReady = Boolean(db?.ok);
    res.status(dbReady ? 200 : 503).json({
      ok: dbReady,
      dbReady,
      sourceMode: process.env.SOURCE_MODE || 'demo',
      startupError: startupError?.message || null
    });
  } catch (error) {
    dbReady = false;
    startupError = error;
    res.status(503).json({
      ok: false,
      dbReady: false,
      sourceMode: process.env.SOURCE_MODE || 'demo',
      startupError: error.message
    });
  }
});

app.use('/api', (req, res, next) => {
  if (req.path === '/health') return next();
  if (!dbReady) {
    return res.status(503).json({
      error: 'Base de datos no inicializada',
      detail: startupError?.message || 'Revisa variables DB_HOST, DB_USER, DB_PASSWORD y DB_NAME'
    });
  }
  return next();
});

app.post('/api/auth/login', async (req, res) => {
  const { email, password } = req.body || {};
  const user = await verifyLogin(email, password);
  if (!user) return res.status(401).json({ error: 'Credenciales invalidas' });
  res.json({ token: signToken(user), user });
});

app.get('/api/me', requireAuth, (req, res) => {
  res.json({ user: req.user });
});

app.get('/api/dashboard', requireAuth, async (_req, res) => {
  const [metrics, jobs, recentEvents, revenue] = await Promise.all([
    dashboardMetrics(),
    query('select status, count(*) as total from crawl_jobs group by status'),
    query(
      `select id, process_id, event_type, severity, excerpt, created_at
       from process_events
       order by created_at desc
       limit 8`
    ),
    businessProjection()
  ]);
  res.json({ metrics, jobs, recentEvents, revenue, sourceMode: process.env.SOURCE_MODE || 'demo' });
});

app.get('/api/processes', requireAuth, async (req, res) => {
  const search = String(req.query.search || '').trim();
  const params = [];
  let where = '';
  if (search) {
    where = `where process_id like ? or city like ? or process_type like ? or current_status like ?`;
    params.push(...Array(4).fill(`%${search}%`));
  }
  const rows = await query(
    `select id, process_id, court, city, process_type, current_status, risk_score, updated_at
     from monitored_processes
     ${where}
     order by risk_score desc, updated_at desc
     limit 100`,
    params
  );
  res.json({ rows });
});

app.get('/api/events', requireAuth, async (_req, res) => {
  const rows = await query(
    `select id, process_id, event_type, severity, excerpt, delivered_at, created_at
     from process_events
     order by created_at desc
     limit 100`
  );
  res.json({ rows });
});

app.post('/api/processes/import', requireAuth, async (req, res) => {
  const body = req.body || {};
  const processId = normalizeRadicado(body.process_id);
  if (!processId || !body.status_text) {
    return res.status(400).json({ error: 'process_id y status_text son requeridos' });
  }
  const eventCount = await upsertSnapshot({
    process_id: processId,
    court: body.court || null,
    city: body.city || null,
    process_type: body.process_type || null,
    parties: body.parties || null,
    status_text: String(body.status_text),
    source_url: body.source_url || 'manual-import',
    raw: {
      process_id: processId,
      court: body.court || null,
      city: body.city || null,
      process_type: body.process_type || null,
      parties: body.parties || null,
      status_text: String(body.status_text),
      source_url: body.source_url || 'manual-import',
      imported_by: req.user.email
    }
  });
  res.json({ ok: true, process_id: processId, eventCount });
});

app.get('/api/clients', requireAuth, async (_req, res) => {
  const rows = await query(
    `select id, name, email, plan, status, monthly_price_cop, created_at
     from clients
     order by created_at desc
     limit 200`
  );
  res.json({ rows });
});

app.post('/api/clients', requireAuth, requireAdmin, async (req, res) => {
  const body = req.body || {};
  if (!body.name || !body.email) return res.status(400).json({ error: 'Nombre y email requeridos' });
  const priceByPlan = { starter: 249000, pro: 799000, enterprise: 3500000 };
  const plan = ['starter', 'pro', 'enterprise'].includes(body.plan) ? body.plan : 'starter';
  await query(
    `insert into clients (name, email, plan, monthly_price_cop)
     values (?, ?, ?, ?)
     on duplicate key update
       name = values(name),
       plan = values(plan),
       monthly_price_cop = values(monthly_price_cop),
       status = 'active'`,
    [body.name, body.email, plan, Number(body.monthly_price_cop || priceByPlan[plan])]
  );
  res.json({ ok: true });
});

app.patch('/api/clients/:id', requireAuth, requireAdmin, async (req, res) => {
  await query(
    `update clients set status = ?, plan = ?, monthly_price_cop = ? where id = ?`,
    [
      req.body.status || 'active',
      req.body.plan || 'starter',
      Number(req.body.monthly_price_cop || 249000),
      req.params.id
    ]
  );
  res.json({ ok: true });
});

app.get('/api/jobs', requireAuth, async (_req, res) => {
  const rows = await query(
    `select id, source_key, job_type, lookup_key, priority, status, attempts, max_attempts,
            run_after, leased_by, leased_until, last_error, updated_at
     from crawl_jobs
     order by field(status, 'queued','leased','failed','dead','done'), priority asc, updated_at desc
     limit 200`
  );
  res.json({ rows });
});

app.post('/api/jobs/enqueue', requireAuth, async (req, res) => {
  const radicado = normalizeRadicado(req.body?.radicado);
  if (!radicado) return res.status(400).json({ error: 'Radicado requerido' });
  await enqueueRadicado(radicado, { created_from: 'dashboard' }, 50, req.user.email);
  res.json({ ok: true, radicado });
});

app.post('/api/jobs/demo-seed', requireAuth, async (req, res) => {
  const count = Math.min(Number(req.body?.count || 8), 50);
  const inserted = [];
  for (let i = 0; i < count; i += 1) {
    const radicado = `110013103${String(i + 1).padStart(3, '0')}2024${String(1200 + i).padStart(5, '0')}00`;
    await enqueueRadicado(radicado, { created_from: 'demo_seed' }, 80, req.user.email);
    inserted.push(radicado);
  }
  res.json({ ok: true, inserted });
});

app.post('/api/worker/tick', requireAuth, requireAdmin, async (_req, res) => {
  const result = await processOneJob(`manual-${Date.now()}`);
  res.json(result);
});

app.post('/api/cron/tick', async (req, res) => {
  if (!process.env.CRON_SECRET || req.query.secret !== process.env.CRON_SECRET) {
    return res.status(403).json({ error: 'CRON_SECRET invalido' });
  }
  const result = await processOneJob(`cron-${Date.now()}`);
  res.json(result);
});

app.get('/api/rate-limit', requireAuth, async (_req, res) => {
  const rows = await query('select * from source_rate_limits order by source_key');
  res.json({ rows });
});

app.put('/api/rate-limit/:sourceKey', requireAuth, requireAdmin, async (req, res) => {
  await query(
    `update source_rate_limits
     set min_seconds_between_requests = ?, daily_limit = ?
     where source_key = ?`,
    [
      Number(req.body.min_seconds_between_requests || 8),
      Number(req.body.daily_limit || 1500),
      req.params.sourceKey
    ]
  );
  res.json({ ok: true });
});

app.get('/api/compliance/reviews', requireAuth, async (_req, res) => {
  const rows = await query('select * from privacy_review_items order by field(severity, "critical","high","medium","low"), due_at asc');
  res.json({ rows });
});

app.patch('/api/compliance/reviews/:id', requireAuth, requireAdmin, async (req, res) => {
  await query(
    `update privacy_review_items
     set status = ?, owner = ?, closed_at = if(? = 'closed', now(), null)
     where id = ?`,
    [req.body.status || 'open', req.body.owner || null, req.body.status || 'open', req.params.id]
  );
  res.json({ ok: true });
});

app.get('/api/compliance/requests', requireAuth, async (_req, res) => {
  const rows = await query('select * from data_subject_requests order by created_at desc limit 100');
  res.json({ rows });
});

app.post('/api/compliance/requests', requireAuth, async (req, res) => {
  const body = req.body || {};
  await query(
    `insert into data_subject_requests
      (request_type, requester_name, requester_contact, related_process_id, response_due_at, notes)
     values (?, ?, ?, ?, date_add(now(), interval 15 day), ?)`,
    [
      body.request_type || 'claim',
      body.requester_name || null,
      body.requester_contact,
      body.related_process_id || null,
      body.notes || null
    ]
  );
  res.json({ ok: true });
});

app.get('/api/audit', requireAuth, requireAdmin, async (_req, res) => {
  const rows = await query(
    `select actor, action, entity_type, entity_id, lawful_basis, purpose, created_at
     from audit_log
     order by created_at desc
     limit 150`
  );
  res.json({ rows });
});

app.get('/api/alerts/deliveries', requireAuth, async (_req, res) => {
  const rows = await query(
    `select ad.id, ad.channel, ad.status, ad.sent_at, ad.created_at,
            pe.process_id, pe.event_type, pe.severity
     from alert_deliveries ad
     join process_events pe on pe.id = ad.event_id
     order by ad.created_at desc
     limit 150`
  );
  res.json({ rows });
});

app.get('/api/business/projection', requireAuth, async (_req, res) => {
  res.json(await businessProjection());
});

app.get('/api/deploy/hostinger', requireAuth, async (_req, res) => {
  res.json({
    runtime: 'Node.js 20+',
    buildCommand: 'npm install && npm run build',
    startCommand: 'npm start',
    documentRoot: 'dist served by Express',
    variables: ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'JWT_SECRET', 'ADMIN_EMAIL', 'ADMIN_PASSWORD', 'CRON_SECRET', 'SOURCE_MODE']
  });
});

const distPath = path.join(__dirname, '..', 'dist');
app.use(express.static(distPath));
app.get('*', (_req, res) => {
  res.sendFile(path.join(distPath, 'index.html'));
});

app.use((error, _req, res, _next) => {
  console.error('API error:', error);
  res.status(500).json({ error: 'Error interno', detail: error.message });
});

app.listen(port, () => {
  console.log(`PropIntel Judicial listo en puerto ${port}`);
  startWorkerLoop();
});

process.on('SIGTERM', async () => {
  await pool.end();
  process.exit(0);
});

function normalizeRadicado(value = '') {
  return String(value).replace(/[^\dA-Za-z-]/g, '').slice(0, 80);
}

async function dashboardMetrics() {
  const processes = await one('select count(*) as total from monitored_processes');
  const eventsToday = await one('select count(*) as total from process_events where date(created_at) = current_date()');
  const highRisk = await one('select count(*) as total from monitored_processes where risk_score >= 15');
  const queued = await one('select count(*) as total from crawl_jobs where status = "queued"');
  const complianceOpen = await one('select count(*) as total from privacy_review_items where status <> "closed"');
  return {
    processes: Number(processes.total || 0),
    eventsToday: Number(eventsToday.total || 0),
    highRisk: Number(highRisk.total || 0),
    queued: Number(queued.total || 0),
    complianceOpen: Number(complianceOpen.total || 0)
  };
}

async function businessProjection() {
  const clients = await query('select plan, count(*) as total, sum(monthly_price_cop) as revenue from clients where status = "active" group by plan');
  const baseline = {
    starter: { clients: 30, price: 249000 },
    pro: { clients: 15, price: 799000 },
    enterprise: { clients: 3, price: 3500000 }
  };
  const projectedMonthly = Object.values(baseline).reduce((sum, row) => sum + row.clients * row.price, 0);
  const currentMonthly = clients.reduce((sum, row) => sum + Number(row.revenue || 0), 0);
  return { currentMonthly, projectedMonthly, baseline, clients };
}
