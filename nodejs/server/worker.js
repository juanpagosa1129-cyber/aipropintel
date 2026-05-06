import crypto from 'node:crypto';
import * as cheerio from 'cheerio';
import { audit, one, query, withConnection } from './db.js';

const SOURCE_KEY = 'rama_judicial_cpnu';
const CPNU_URL = 'https://consultaprocesos.ramajudicial.gov.co/Procesos/NumeroRadicacion';
const IMPORTANT_TERMS = {
  embargo: 7,
  secuestro: 8,
  avaluo: 8,
  'avalúo': 8,
  remate: 10,
  pertenencia: 7,
  hipotecario: 7,
  adjudicacion: 9,
  'adjudicación': 9,
  sentencia: 5
};

function hash(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function normalize(value = '') {
  return String(value).replace(/\s+/g, ' ').trim();
}

function cacheKey(job) {
  return hash(`${job.source_key}:${job.job_type}:${job.lookup_key}`);
}

export async function enqueueRadicado(radicado, payload = {}, priority = 100, actor = 'system') {
  await query(
    `insert into crawl_jobs
      (source_key, job_type, lookup_key, payload, priority, max_attempts)
     values (?, 'radicado', ?, ?, ?, 5)
     on duplicate key update
      status = if(status in ('done','failed','dead'), 'queued', status),
      run_after = least(run_after, now()),
      priority = least(priority, values(priority)),
      payload = values(payload)`,
    [SOURCE_KEY, radicado, JSON.stringify(payload), priority]
  );
  await audit({ actor, action: 'enqueue', entityType: 'crawl_job', entityId: radicado, metadata: { job_type: 'radicado' } });
}

export async function leaseJob(workerId) {
  return withConnection(async (conn) => {
    await conn.beginTransaction();
    const [rows] = await conn.query(
      `select id, source_key, job_type, lookup_key, payload, attempts, max_attempts
       from crawl_jobs
       where status = 'queued' and run_after <= now()
       order by priority asc, id asc
       limit 1
       for update skip locked`
    );
    if (!rows.length) {
      await conn.commit();
      return null;
    }
    const job = rows[0];
    await conn.execute(
      `update crawl_jobs
       set status = 'leased',
           attempts = attempts + 1,
           leased_by = ?,
           leased_until = date_add(now(), interval 5 minute)
       where id = ?`,
      [workerId, job.id]
    );
    await conn.commit();
    const payload = typeof job.payload === 'string' ? JSON.parse(job.payload || '{}') : (job.payload || {});
    return { ...job, payload, attempts: job.attempts + 1 };
  });
}

export async function completeJob(job, eventCount) {
  await query(
    `update crawl_jobs
     set status = 'done', leased_by = null, leased_until = null, last_error = null
     where id = ?`,
    [job.id]
  );
  await audit({ action: 'complete', entityType: 'crawl_job', entityId: String(job.id), metadata: { lookup_key: job.lookup_key, event_count: eventCount } });
}

export async function failJob(job, error) {
  const dead = job.attempts >= job.max_attempts;
  const backoffSeconds = Math.min(14400, 60 * 2 ** Math.min(job.attempts, 8));
  await query(
    `update crawl_jobs
     set status = ?,
         leased_by = null,
         leased_until = null,
         run_after = date_add(now(), interval ? second),
         last_error = ?
     where id = ?`,
    [dead ? 'dead' : 'queued', backoffSeconds, String(error.message || error).slice(0, 1000), job.id]
  );
  await audit({
    action: dead ? 'dead_letter' : 'retry',
    entityType: 'crawl_job',
    entityId: String(job.id),
    metadata: { lookup_key: job.lookup_key, error: String(error.message || error).slice(0, 500) }
  });
}

export async function consumeRateLimit() {
  while (true) {
    const row = await one('select * from source_rate_limits where source_key = ?', [SOURCE_KEY]);
    if (!row) throw new Error('No existe rate limit para la fuente');
    if (String(row.day).slice(0, 10) !== new Date().toISOString().slice(0, 10)) {
      await query('update source_rate_limits set day = current_date(), requests_today = 0 where source_key = ?', [SOURCE_KEY]);
      continue;
    }
    if (row.requests_today >= row.daily_limit) {
      throw new Error(`Cuota diaria agotada para ${SOURCE_KEY}`);
    }
    if (row.last_request_at) {
      const elapsed = (Date.now() - new Date(row.last_request_at).getTime()) / 1000;
      if (elapsed < row.min_seconds_between_requests) {
        await new Promise((resolve) => setTimeout(resolve, (row.min_seconds_between_requests - elapsed) * 1000));
      }
    }
    await query(
      `update source_rate_limits
       set requests_today = requests_today + 1, last_request_at = now()
       where source_key = ?`,
      [SOURCE_KEY]
    );
    await audit({ action: 'rate_limit_consume', entityType: 'source', entityId: SOURCE_KEY });
    return;
  }
}

export async function getCachedHtml(job) {
  const key = cacheKey(job);
  const row = await one('select html from crawl_cache where cache_key = ? and expires_at > now()', [key]);
  await audit({ action: row ? 'cache_hit' : 'cache_miss', entityType: 'crawl_cache', entityId: key, metadata: { lookup_key: job.lookup_key } });
  return row?.html || null;
}

export async function putCachedHtml(job, html) {
  const key = cacheKey(job);
  const ttl = Number(process.env.CACHE_TTL_HOURS || 12);
  await query(
    `insert into crawl_cache
      (cache_key, source_key, lookup_key, content_hash, html, metadata, expires_at)
     values (?, ?, ?, ?, ?, ?, date_add(now(), interval ? hour))
     on duplicate key update
      content_hash = values(content_hash),
      html = values(html),
      metadata = values(metadata),
      expires_at = values(expires_at)`,
    [key, job.source_key, job.lookup_key, hash(html), html, JSON.stringify({ ttl_hours: ttl, source_url: CPNU_URL }), ttl]
  );
}

export async function fetchSourceHtml(job) {
  const mode = process.env.SOURCE_MODE || 'demo';
  if (mode === 'demo') return demoHtml(job.lookup_key);
  if (mode === 'cpnu') {
    await consumeRateLimit();
    const response = await fetch(CPNU_URL, {
      headers: {
        'user-agent': 'PropIntelJudicial/1.0 contacto: cumplimiento@propintel.co',
        accept: 'text/html,application/xhtml+xml'
      }
    });
    const html = await response.text();
    return html.includes(job.lookup_key) ? html : htmlWithNotice(job.lookup_key, html);
  }
  throw new Error(`SOURCE_MODE no soportado: ${mode}`);
}

function htmlWithNotice(radicado, html) {
  const text = normalize(cheerio.load(html).text()).slice(0, 2500);
  return `<table><tr><th>Radicado</th><th>Estado</th><th>Fuente</th></tr><tr><td>${radicado}</td><td>Consulta CPNU recibida. La interfaz publica puede requerir sesion dinamica; revisar conector Playwright dedicado.</td><td>${text}</td></tr></table>`;
}

function demoHtml(radicado) {
  const endings = ['embargo decretado', 'avaluo aprobado', 'secuestro del bien', 'señalamiento de remate', 'mandamiento de pago'];
  const idx = Math.abs([...radicado].reduce((acc, char) => acc + char.charCodeAt(0), 0)) % endings.length;
  const city = ['Bogota', 'Medellin', 'Cali', 'Barranquilla', 'Bucaramanga'][idx];
  const type = idx % 2 === 0 ? 'Ejecutivo hipotecario' : 'Pertenencia';
  return `
    <table>
      <thead>
        <tr><th>Radicado</th><th>Despacho</th><th>Ciudad</th><th>Clase de Proceso</th><th>Sujetos Procesales</th><th>Fecha Actuacion</th><th>Estado</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>${radicado}</td>
          <td>Juzgado ${idx + 1} Civil del Circuito</td>
          <td>${city}</td>
          <td>${type}</td>
          <td>Demandante reservado / Demandado reservado</td>
          <td>${new Date().toISOString().slice(0, 10)}</td>
          <td>Auto: ${endings[idx]} sobre inmueble urbano. Pendiente revision de fuente oficial.</td>
        </tr>
      </tbody>
    </table>`;
}

export function parseSnapshots(html, fallbackProcessId) {
  const $ = cheerio.load(html);
  const rows = [];
  $('table').each((_, table) => {
    const headers = [];
    $(table).find('th').each((__, th) => headers.push(normalize($(th).text())));
    $(table).find('tr').each((__, tr) => {
      const cells = [];
      $(tr).find('td').each((___, td) => cells.push(normalize($(td).text())));
      if (!cells.length) return;
      const row = {};
      cells.forEach((cell, idx) => {
        row[headers[idx] || `col_${idx}`] = cell;
      });
      rows.push(row);
    });
  });
  if (!rows.length) {
    return [{
      process_id: fallbackProcessId,
      court: null,
      city: null,
      process_type: null,
      parties: null,
      status_text: normalize($.text()).slice(0, 4000),
      source_url: CPNU_URL,
      raw: { html_text: normalize($.text()).slice(0, 4000) }
    }];
  }
  return rows.map((row) => rowToSnapshot(row, fallbackProcessId));
}

function rowToSnapshot(row, fallbackProcessId) {
  const lower = Object.fromEntries(Object.entries(row).map(([key, value]) => [normalize(key).toLowerCase(), value]));
  const processId = lower.radicado || lower['numero de radicacion'] || lower.proceso || fallbackProcessId;
  const status = Object.values(row).filter(Boolean).join(' | ');
  return {
    process_id: normalize(processId),
    court: lower.despacho || lower.juzgado || null,
    city: lower.ciudad || lower.municipio || null,
    process_type: lower['clase de proceso'] || lower['tipo proceso'] || null,
    parties: lower['sujetos procesales'] || lower['demandante / demandado'] || null,
    status_text: normalize(status),
    source_url: CPNU_URL,
    raw: row
  };
}

function detectEvents(snapshot, previous) {
  const text = `${snapshot.process_type || ''} ${snapshot.status_text}`.toLowerCase();
  const changed = previous?.content_hash !== snapshot.content_hash;
  return Object.entries(IMPORTANT_TERMS)
    .filter(([term]) => text.includes(term) && (changed || !previous?.current_status?.toLowerCase().includes(term)))
    .map(([term, severity]) => ({
      process_id: snapshot.process_id,
      event_type: term,
      severity,
      excerpt: snapshot.status_text.slice(Math.max(0, text.indexOf(term) - 120), 360),
      previous_hash: previous?.content_hash || null,
      current_hash: snapshot.content_hash
    }));
}

export async function upsertSnapshot(snapshot) {
  const contentHash = hash(JSON.stringify(snapshot.raw));
  snapshot.content_hash = contentHash;
  const previous = await one('select current_status, content_hash from monitored_processes where process_id = ?', [snapshot.process_id]);
  const riskScore = Math.min(100, Object.entries(IMPORTANT_TERMS).reduce((score, [term, value]) => {
    return snapshot.status_text.toLowerCase().includes(term) ? score + value : score;
  }, 0));
  await query(
    `insert into monitored_processes
      (process_id, court, city, process_type, parties, current_status, source_url, content_hash, risk_score)
     values (?, ?, ?, ?, ?, ?, ?, ?, ?)
     on duplicate key update
      court = values(court),
      city = values(city),
      process_type = values(process_type),
      parties = values(parties),
      current_status = values(current_status),
      source_url = values(source_url),
      content_hash = values(content_hash),
      risk_score = values(risk_score)`,
    [
      snapshot.process_id,
      snapshot.court,
      snapshot.city,
      snapshot.process_type,
      snapshot.parties,
      snapshot.status_text,
      snapshot.source_url,
      contentHash,
      riskScore
    ]
  );
  await query(
    `insert ignore into process_snapshots (process_id, content_hash, status_text, raw)
     values (?, ?, ?, ?)`,
    [snapshot.process_id, contentHash, snapshot.status_text, JSON.stringify(snapshot.raw)]
  );
  const events = detectEvents(snapshot, previous);
  for (const event of events) {
    const result = await query(
      `insert into process_events
        (process_id, event_type, severity, excerpt, previous_hash, current_hash)
       values (?, ?, ?, ?, ?, ?)`,
      [event.process_id, event.event_type, event.severity, event.excerpt, event.previous_hash, event.current_hash]
    );
    await query(
      `insert into alert_deliveries (event_id, channel, status, payload)
       values (?, 'dashboard', 'sent', ?)`,
      [result.insertId, JSON.stringify(event)]
    );
    await audit({ action: 'event_detected', entityType: 'process_event', entityId: event.process_id, metadata: event });
    await sendTelegram(event);
  }
  await audit({ action: 'snapshot_upsert', entityType: 'monitored_process', entityId: snapshot.process_id, metadata: { risk_score: riskScore, content_hash: contentHash } });
  return events.length;
}

async function sendTelegram(event) {
  if (!process.env.TELEGRAM_BOT_TOKEN || !process.env.TELEGRAM_CHAT_ID) return;
  await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      chat_id: process.env.TELEGRAM_CHAT_ID,
      text: `Alerta judicial inmobiliaria\nProceso: ${event.process_id}\nEvento: ${event.event_type}\nSeveridad: ${event.severity}/10\n${event.excerpt}`
    })
  }).catch(() => null);
}

export async function processOneJob(workerId = `web-${process.pid}`) {
  const job = await leaseJob(workerId);
  if (!job) return { processed: false, message: 'Sin trabajos pendientes' };
  try {
    let html = await getCachedHtml(job);
    if (!html) {
      html = await fetchSourceHtml(job);
      await putCachedHtml(job, html);
    }
    const snapshots = parseSnapshots(html, job.lookup_key);
    let eventCount = 0;
    for (const snapshot of snapshots) eventCount += await upsertSnapshot(snapshot);
    await completeJob(job, eventCount);
    return { processed: true, jobId: job.id, lookupKey: job.lookup_key, eventCount };
  } catch (error) {
    await failJob(job, error);
    throw error;
  }
}

export function startWorkerLoop() {
  if (process.env.WORKER_ENABLED !== 'true') return;
  const interval = Number(process.env.WORKER_INTERVAL_SECONDS || 60) * 1000;
  setInterval(async () => {
    try {
      await processOneJob(`interval-${process.pid}`);
    } catch (error) {
      console.error('Worker error:', error.message);
    }
  }, interval).unref();
}
