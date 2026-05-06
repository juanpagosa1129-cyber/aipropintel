const api = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error API");
    return data;
  },
};

let processes = [];
let alerts = [];
let sourceRuns = [];
let opportunities = [];
let watchlists = [];
let selected = null;
let stream = null;

const cityXY = {
  bogota: [52, 43],
  medellin: [44, 34],
  cali: [37, 53],
  barranquilla: [50, 18],
  cartagena: [43, 20],
  bucaramanga: [60, 34],
  pereira: [40, 45],
  ibague: [45, 49],
  cucuta: [67, 31],
  villavicencio: [58, 48],
};

const colombiaSvg = `
  <svg class="colombia-svg" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    <defs>
      <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#d2eee6"></stop>
        <stop offset="100%" stop-color="#bfe5dc"></stop>
      </linearGradient>
    </defs>
    <path d="M45 5 L58 12 L63 22 L72 27 L70 36 L77 43 L74 56 L66 63 L64 75 L55 86 L46 93 L35 88 L28 77 L23 67 L27 56 L21 49 L24 38 L18 31 L24 24 L29 15 L37 10 Z" fill="url(#g1)" stroke="#7fb7aa" stroke-width="1.2"></path>
    <circle cx="52" cy="43" r="1.3" fill="#2f6b61"></circle>
    <text x="54" y="42" font-size="2.6" fill="#2f6b61">Bogota</text>
    <text x="50" y="18" font-size="2.3" fill="#436a62">Caribe</text>
    <text x="30" y="57" font-size="2.3" fill="#436a62">Pacifico</text>
    <text x="60" y="56" font-size="2.3" fill="#436a62">Andina</text>
    <text x="67" y="76" font-size="2.3" fill="#436a62">Orinoquia</text>
  </svg>
`;

function money(value) {
  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function safeCityKey(city) {
  return String(city || "")
    .toLowerCase()
    .replaceAll(" ", "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function statusTag(value) {
  if (value === "ok") return "ok";
  if (value === "blocked_interactive") return "blocked";
  if (value === "error") return "error";
  return "neutral";
}

function statusText(value) {
  if (value === "ok") return "ok";
  if (value === "blocked_interactive") return "bloqueado";
  if (value === "error") return "error";
  if (value === "idle") return "en espera";
  return "sin datos";
}

function toast(message) {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2200);
}

function setView(id) {
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === id));
  document.querySelectorAll(".nav").forEach((item) => item.classList.toggle("active", item.dataset.view === id));
  const labels = {
    dashboard: "Panel ejecutivo",
    live: "Busqueda oficial en vivo",
    opportunities: "Top oportunidades",
    map: "Mapa GIS Colombia",
    alerts: "Alertas de seguimiento",
    watchlists: "Watchlists",
    business: "Modelo de negocio",
    processes: "Registro de proceso",
    import: "Importacion y normalizacion",
  };
  document.querySelector("#title").textContent = labels[id] || "Propintel IA";
  if (id === "map") renderMap();
}

function renderAnalytics(analytics) {
  document.querySelector("#m-total").textContent = analytics.total_processes || 0;
  document.querySelector("#m-geo").textContent = analytics.geocoded_properties || 0;
  document.querySelector("#m-risk").textContent = `${analytics.average_risk || 0}%`;
  document.querySelector("#m-alerts").textContent = analytics.critical_alerts || 0;
}

function renderSourceStatus(status) {
  const latest = status.latest_run;
  const state = latest?.status || "neutral";
  const tag = document.querySelector("#source-tag");
  tag.className = `status ${statusTag(state)}`;
  tag.textContent = statusText(state);
  document.querySelector("#source-message").textContent = status.message || "Sin mensaje.";
  document.querySelector("#source-details").textContent = latest
    ? `Ultima: ${latest.created_at} | Modo: ${latest.mode} | Importados: ${latest.imported_count} | Intervencion humana: ${latest.requires_human_intervention ? "si" : "no"}`
    : "No hay corridas registradas.";
}

function renderSourceRuns() {
  const box = document.querySelector("#source-runs");
  box.innerHTML =
    sourceRuns
      .map(
        (run) => `
      <article class="event">
        <strong>${run.mode} | <span class="status-inline ${statusTag(run.status)}">${statusText(run.status)}</span></strong>
        <span>${run.created_at}</span>
        <span>${run.message || ""}</span>
      </article>
    `
      )
      .join("") || `<p class="muted">Sin ejecuciones de fuente.</p>`;
}

function renderBot(bot) {
  document.querySelector("#bot-interval").value = bot.interval_minutes || 1440;
  document.querySelector("#bot-enabled").checked = !!bot.enabled;
  const tag = document.querySelector("#bot-tag");
  tag.className = `status ${statusTag(bot.last_status)}`;
  tag.textContent = statusText(bot.last_status);
  document.querySelector("#bot-message").textContent =
    `Ultima: ${bot.last_run_at || "nunca"} | Estado: ${statusText(bot.last_status)} | ${bot.last_message || ""} | Importados: ${bot.last_imported || 0}`;
}

function renderProcesses() {
  const tbody = document.querySelector("#process-table");
  tbody.innerHTML =
    processes
      .map(
        (p) => `
      <tr>
        <td><strong>${p.numero_proceso}</strong><br><small>${p.juzgado || "Sin juzgado"}</small></td>
        <td>${p.ciudad}</td>
        <td>${p.tipo_proceso}</td>
        <td>${p.estado}</td>
        <td><span class="chip ${p.risk_level}">${p.risk_score}% ${p.risk_level}</span></td>
      </tr>
    `
      )
      .join("") || `<tr><td colspan="5">Sin procesos para mostrar.</td></tr>`;
}

function renderAlerts() {
  document.querySelector("#alerts-list").innerHTML =
    alerts
      .map(
        (a) => `
      <article class="card">
        <span class="chip ${a.risk_level}">${a.risk_score}% ${a.risk_level}</span>
        <h3>${a.ciudad} | ${a.tipo_proceso}</h3>
        <p class="muted">${a.message}</p>
        <strong>${a.numero_proceso}</strong>
      </article>
    `
      )
      .join("") || `<p class="muted">No hay alertas activas.</p>`;
}

function renderOpportunities() {
  const tbody = document.querySelector("#opportunity-table");
  tbody.innerHTML =
    opportunities
      .map(
        (o) => `
      <tr>
        <td>${o.numero_proceso}</td>
        <td>${o.ciudad}</td>
        <td>${o.tipo_proceso}</td>
        <td>${o.estado}</td>
        <td>${money(o.avaluo)}</td>
        <td><span class="chip ${o.risk_level}">${o.risk_score}% ${o.risk_level}</span></td>
      </tr>
    `
      )
      .join("") || `<tr><td colspan="6">Sin oportunidades para el umbral actual.</td></tr>`;
}

function renderCityFilter() {
  const select = document.querySelector("#city-filter");
  const current = select.value;
  const cities = [...new Set(processes.map((p) => p.ciudad))].sort();
  select.innerHTML = `<option value="">Todas las ciudades</option>${cities.map((city) => `<option>${city}</option>`).join("")}`;
  select.value = cities.includes(current) ? current : "";
}

function renderMap() {
  const map = document.querySelector("#map-canvas");
  const filter = document.querySelector("#city-filter").value;
  const rows = processes.filter((p) => !filter || p.ciudad === filter);
  map.innerHTML = colombiaSvg;

  rows.forEach((item, idx) => {
    const key = safeCityKey(item.ciudad);
    const point = cityXY[key] || [50 + (idx % 4) * 2, 46 + (idx % 3) * 3];
    const marker = document.createElement("button");
    marker.className = `marker ${item.risk_level}`;
    marker.style.left = `${point[0] + (idx % 3) * 1.3}%`;
    marker.style.top = `${point[1] + (idx % 2) * 1.4}%`;
    marker.title = `${item.ciudad} - ${item.risk_score}%`;
    marker.addEventListener("click", () => {
      selected = item;
      renderDetail();
    });
    map.appendChild(marker);
  });

  if (!selected && rows[0]) selected = rows[0];
  renderDetail();
}

function renderDetail() {
  const box = document.querySelector("#detail");
  if (!selected) {
    box.textContent = "Selecciona un punto del mapa.";
    return;
  }
  box.innerHTML = `
    <dl>
      <div><dt>Proceso</dt><dd>${selected.numero_proceso}</dd></div>
      <div><dt>Ciudad</dt><dd>${selected.ciudad}</dd></div>
      <div><dt>Direccion</dt><dd>${selected.direccion}</dd></div>
      <div><dt>Tipo</dt><dd>${selected.tipo_proceso}</dd></div>
      <div><dt>Estado</dt><dd>${selected.estado}</dd></div>
      <div><dt>Avaluo</dt><dd>${money(selected.avaluo)}</dd></div>
      <div><dt>Riesgo</dt><dd>${selected.risk_score}% ${selected.risk_level}</dd></div>
      <div><dt>Fuente</dt><dd>${selected.source || "manual"}</dd></div>
      <div><dt>Actualizado</dt><dd>${selected.updated_at || "-"}</dd></div>
    </dl>
  `;
}

function renderLiveResults(items) {
  const target = document.querySelector("#live-results");
  if (!items || !items.length) {
    target.innerHTML = `<p class="muted">Sin registros retornados por la consulta oficial.</p>`;
    return;
  }
  target.innerHTML = `
    <table>
      <thead><tr><th>Proceso</th><th>Ciudad</th><th>Tipo</th><th>Estado</th><th>Avaluo</th><th>Riesgo</th></tr></thead>
      <tbody>
        ${items
          .map(
            (row) => `
          <tr>
            <td>${row.numero_proceso}</td>
            <td>${row.ciudad}</td>
            <td>${row.tipo_proceso}</td>
            <td>${row.estado}</td>
            <td>${money(row.avaluo)}</td>
            <td><span class="chip ${row.risk_level}">${row.risk_score}% ${row.risk_level}</span></td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderWatchlists() {
  const list = document.querySelector("#watchlists-list");
  list.innerHTML =
    watchlists
      .map(
        (w) => `
      <article class="event">
        <strong>${w.name}</strong>
        <span>Owner: ${w.owner} | Activa: ${w.active ? "si" : "no"}</span>
        <span>Criterios: ${JSON.stringify(w.criteria)}</span>
        <div class="row-actions">
          <button data-run-watchlist="${w.id}">Ejecutar</button>
          <button data-del-watchlist="${w.id}">Eliminar</button>
        </div>
      </article>
    `
      )
      .join("") || `<p class="muted">Sin watchlists creadas.</p>`;

  document.querySelectorAll("[data-run-watchlist]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.getAttribute("data-run-watchlist"));
      const result = await api.post("/api/watchlists/run", { id, limit: 120 });
      renderWatchlistResults(result.matches || []);
      toast(`Watchlist ejecutada: ${result.count} coincidencias`);
    });
  });

  document.querySelectorAll("[data-del-watchlist]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.getAttribute("data-del-watchlist"));
      await api.post("/api/watchlists/delete", { id });
      toast("Watchlist eliminada");
      await loadWatchlists();
    });
  });
}

function renderWatchlistResults(items) {
  const el = document.querySelector("#watchlist-results");
  if (!items.length) {
    el.innerHTML = `<p class="muted">Sin coincidencias para esta watchlist.</p>`;
    return;
  }
  el.innerHTML = `
    <table>
      <thead><tr><th>Proceso</th><th>Ciudad</th><th>Tipo</th><th>Estado</th><th>Riesgo</th></tr></thead>
      <tbody>
        ${items
          .map(
            (item) => `
          <tr>
            <td>${item.numero_proceso}</td>
            <td>${item.ciudad}</td>
            <td>${item.tipo_proceso}</td>
            <td>${item.estado}</td>
            <td><span class="chip ${item.risk_level}">${item.risk_score}% ${item.risk_level}</span></td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderBusinessProjection(data) {
  document.querySelector("#biz-result").innerHTML = `
    <article><span>MRR</span><strong>${money(data.mrr)}</strong></article>
    <article><span>ARR</span><strong>${money(data.arr)}</strong></article>
    <article><span>Basico</span><strong>${money(data.breakdown.basic)}</strong></article>
    <article><span>Profesional</span><strong>${money(data.breakdown.pro)}</strong></article>
  `;
}

async function loadProcesses() {
  const risk = document.querySelector("#risk-filter").value;
  const q = document.querySelector("#search-q").value.trim();
  const payload = await api.get(`/api/processes?risk=${encodeURIComponent(risk)}&q=${encodeURIComponent(q)}&limit=300`);
  processes = payload.items || [];
  renderProcesses();
  renderCityFilter();
  renderMap();
}

async function loadOpportunities() {
  const minScore = Number(document.querySelector("#op-min-score").value || 70);
  const payload = await api.get(`/api/opportunities?min_score=${encodeURIComponent(minScore)}&limit=120`);
  opportunities = payload.items || [];
  renderOpportunities();
}

async function loadWatchlists() {
  const payload = await api.get("/api/watchlists");
  watchlists = payload.items || [];
  renderWatchlists();
}

async function loadAll() {
  try {
    const [health, analytics, alertPayload, sourceStatus, runsPayload, botConfig] = await Promise.all([
      api.get("/api/health"),
      api.get("/api/analytics"),
      api.get("/api/alerts?limit=300"),
      api.get("/api/source/status"),
      api.get("/api/source/runs?limit=30"),
      api.get("/api/bot/config"),
    ]);
    alerts = alertPayload.items || [];
    sourceRuns = runsPayload.items || [];

    document.querySelector("#health").textContent = health.status === "ok" ? "Operativa" : "Sin conexion";
    renderAnalytics(analytics);
    renderSourceStatus(sourceStatus);
    renderSourceRuns();
    renderBot(botConfig);
    renderAlerts();
    await loadProcesses();
    await loadOpportunities();
    await loadWatchlists();
  } catch (err) {
    document.querySelector("#health").textContent = "Sin conexion";
    toast(err.message);
  }
}

function connectStream() {
  if (stream) {
    stream.close();
  }
  stream = new EventSource("/api/stream/events");
  stream.addEventListener("state", (event) => {
    try {
      const payload = JSON.parse(event.data);
      renderAnalytics(payload.analytics || {});
      const source = payload.source_status || {};
      if (source.latest_run) {
        renderSourceStatus(source);
      }
    } catch {
      return;
    }
  });
  stream.onerror = () => {
    if (stream) stream.close();
    setTimeout(connectStream, 4000);
  };
}

document.querySelectorAll(".nav").forEach((el) => el.addEventListener("click", () => setView(el.dataset.view)));

document.querySelector("#refresh").addEventListener("click", loadAll);
document.querySelector("#risk-filter").addEventListener("change", loadProcesses);
document.querySelector("#search-q").addEventListener("input", () => {
  clearTimeout(window.__qTimer);
  window.__qTimer = setTimeout(loadProcesses, 250);
});
document.querySelector("#city-filter").addEventListener("change", renderMap);

document.querySelector("#save-bot").addEventListener("click", async () => {
  const interval_minutes = Number(document.querySelector("#bot-interval").value || 1440);
  const enabled = document.querySelector("#bot-enabled").checked;
  await api.post("/api/bot/config", { interval_minutes, enabled });
  toast("Configuracion del bot guardada");
  await loadAll();
});

document.querySelector("#run-bot").addEventListener("click", async () => {
  const result = await api.post("/api/bot/run-now", {});
  toast(`Bot ejecutado: ${statusText(result.last_status)}`);
  await loadAll();
});

document.querySelector("#live-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.target).entries());
  document.querySelector("#live-status").textContent = "Consultando fuente oficial...";
  const result = await api.post("/api/live/search", payload);
  if (result.status === "blocked_interactive") {
    document.querySelector("#live-status").textContent =
      "Consulta bloqueada por control interactivo. Se registro para intervencion humana.";
    renderLiveResults([]);
    toast("Bloqueado por control interactivo");
  } else if (result.status === "error") {
    document.querySelector("#live-status").textContent = `Error de fuente: ${result.message || "sin detalle"}`;
    renderLiveResults([]);
    toast("Error en consulta oficial");
  } else {
    document.querySelector("#live-status").textContent = `Consulta completada. Importados: ${result.imported}.`;
    renderLiveResults(result.items || []);
    toast("Consulta completada");
  }
  await loadAll();
});

document.querySelector("#load-opportunities").addEventListener("click", loadOpportunities);

document.querySelector("#watchlist-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = Object.fromEntries(new FormData(event.target).entries());
  const criteria = {
    city: form.city || undefined,
    risk: form.risk || undefined,
    status: form.status || undefined,
    process_type: form.process_type || undefined,
    text: form.text || undefined,
    min_score: form.min_score ? Number(form.min_score) : undefined,
  };
  Object.keys(criteria).forEach((key) => criteria[key] === undefined && delete criteria[key]);
  await api.post("/api/watchlists", {
    name: form.name,
    owner: form.owner || "equipo",
    criteria,
  });
  event.target.reset();
  toast("Watchlist creada");
  await loadWatchlists();
});

document.querySelector("#biz-calc").addEventListener("click", async () => {
  const basic = Number(document.querySelector("#biz-basic").value || 0);
  const pro = Number(document.querySelector("#biz-pro").value || 0);
  const enterprise = Number(document.querySelector("#biz-enterprise").value || 0);
  const enterprise_ticket = Number(document.querySelector("#biz-ticket").value || 3000000);
  const result = await api.get(
    `/api/business/projection?basic=${basic}&pro=${pro}&enterprise=${enterprise}&enterprise_ticket=${enterprise_ticket}`
  );
  renderBusinessProjection(result);
});

document.querySelector("#process-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.target).entries());
  await api.post("/api/processes", payload);
  event.target.reset();
  toast("Proceso guardado");
  await loadAll();
  setView("dashboard");
});

document.querySelector("#load-sample").addEventListener("click", () => {
  document.querySelector("#csv-text").value =
    "numero_proceso,juzgado,ciudad,direccion,tipo_proceso,estado,avaluo,edad_meses,demandados,acreedores,matricula_inmobiliaria,lat,lng\n" +
    "11001310301820210042100,Juzgado 18 Civil Circuito,Bogota,Calle 93 # 14-20,Ejecutivo hipotecario,Avaluo aprobado,960000000,42,2,1,50C-123456,4.676,-74.048";
});

document.querySelector("#import-csv").addEventListener("click", async () => {
  const csv_text = document.querySelector("#csv-text").value;
  const res = await api.post("/api/import/csv", { csv_text });
  toast(`${res.imported} registros importados`);
  await loadAll();
  setView("dashboard");
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}

loadAll();
connectStream();
