import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  AlertTriangle,
  BriefcaseBusiness,
  CheckCircle2,
  Clock3,
  Database,
  FileSearch,
  Gavel,
  ListChecks,
  Lock,
  LogOut,
  Play,
  RefreshCcw,
  Search,
  ServerCog,
  ShieldCheck,
  Siren,
  Users
} from 'lucide-react';
import './styles.css';

const API = '';

function money(value) {
  return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(value || 0);
}

async function api(path, options = {}) {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      'content-type': 'application/json',
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {})
    }
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    location.reload();
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Error de servidor');
  return data;
}

function Login({ onLogin }) {
  const [email, setEmail] = useState('admin@propintel.co');
  const [password, setPassword] = useState('CambiaEstaClave2026!');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      localStorage.setItem('token', data.token);
      onLogin(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel">
        <div className="brand-row">
          <span className="brand-mark"><Gavel size={24} /></span>
          <div>
            <h1>PropIntel Judicial</h1>
            <p>Inteligencia judicial inmobiliaria</p>
          </div>
        </div>
        <form onSubmit={submit} className="login-form">
          <label>
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" />
          </label>
          <label>
            Clave
            <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" />
          </label>
          {error ? <div className="error-line">{error}</div> : null}
          <button className="primary-button" disabled={loading}>
            <Lock size={18} />
            {loading ? 'Entrando...' : 'Entrar'}
          </button>
        </form>
      </section>
    </main>
  );
}

function App() {
  const [user, setUser] = useState(null);
  const [tab, setTab] = useState('dashboard');

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;
    api('/api/me').then((data) => setUser(data.user)).catch(() => localStorage.removeItem('token'));
  }, []);

  if (!user) return <Login onLogin={setUser} />;

  const tabs = [
    ['dashboard', Activity, 'Panel'],
    ['monitoring', FileSearch, 'Monitoreo'],
    ['queue', ListChecks, 'Cola'],
    ['compliance', ShieldCheck, 'Cumplimiento'],
    ['business', BriefcaseBusiness, 'Negocio'],
    ['deploy', ServerCog, 'Hostinger']
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-row compact">
          <span className="brand-mark"><Gavel size={22} /></span>
          <div>
            <h1>PropIntel</h1>
            <p>Judicial IA</p>
          </div>
        </div>
        <nav>
          {tabs.map(([id, Icon, label]) => (
            <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)} title={label}>
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <button
          className="logout"
          onClick={() => {
            localStorage.removeItem('token');
            setUser(null);
          }}
        >
          <LogOut size={18} />
          Salir
        </button>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">Cloud SaaS</span>
            <h2>{tabs.find(([id]) => id === tab)?.[2]}</h2>
          </div>
          <div className="user-chip">
            <Users size={16} />
            {user.name}
          </div>
        </header>
        {tab === 'dashboard' && <Dashboard />}
        {tab === 'monitoring' && <Monitoring />}
        {tab === 'queue' && <Queue />}
        {tab === 'compliance' && <Compliance />}
        {tab === 'business' && <Business />}
        {tab === 'deploy' && <Deploy />}
      </section>
    </div>
  );
}

function useLoad(loader, deps = []) {
  const [state, setState] = useState({ loading: true, data: null, error: '' });
  async function refresh() {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const data = await loader();
      setState({ loading: false, data, error: '' });
    } catch (error) {
      setState({ loading: false, data: null, error: error.message });
    }
  }
  useEffect(() => {
    refresh();
  }, deps);
  return { ...state, refresh };
}

function Dashboard() {
  const { data, loading, refresh } = useLoad(() => api('/api/dashboard'), []);
  if (loading || !data) return <Loading />;
  const metrics = [
    ['Procesos', data.metrics.processes, Database],
    ['Eventos hoy', data.metrics.eventsToday, Siren],
    ['Alto riesgo', data.metrics.highRisk, AlertTriangle],
    ['En cola', data.metrics.queued, Clock3],
    ['Cumplimiento', data.metrics.complianceOpen, ShieldCheck]
  ];
  return (
    <main className="content-grid">
      <div className="metric-grid">
        {metrics.map(([label, value, Icon]) => (
          <div className="metric" key={label}>
            <Icon size={20} />
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <section className="band two">
        <div>
          <div className="section-title">
            <h3>Eventos recientes</h3>
            <button className="icon-button" onClick={refresh} title="Actualizar"><RefreshCcw size={17} /></button>
          </div>
          <EventList rows={data.recentEvents} />
        </div>
        <div>
          <div className="section-title">
            <h3>Estado comercial</h3>
            <span className="pill">{data.sourceMode}</span>
          </div>
          <div className="revenue-box">
            <span>MRR actual</span>
            <strong>{money(data.revenue.currentMonthly)}</strong>
            <span>Meta base</span>
            <strong>{money(data.revenue.projectedMonthly)}</strong>
          </div>
        </div>
      </section>
    </main>
  );
}

function Monitoring() {
  const [search, setSearch] = useState('');
  const [radicado, setRadicado] = useState('');
  const [manual, setManual] = useState({ process_id: '', city: '', process_type: 'Ejecutivo hipotecario', status_text: '' });
  const [message, setMessage] = useState('');
  const { data, loading, refresh } = useLoad(() => api(`/api/processes?search=${encodeURIComponent(search)}`), [search]);
  const events = useLoad(() => api('/api/events'), []);

  async function enqueue(event) {
    event.preventDefault();
    await api('/api/jobs/enqueue', { method: 'POST', body: JSON.stringify({ radicado }) });
    setRadicado('');
    setMessage('Radicado encolado');
  }

  async function importManual(event) {
    event.preventDefault();
    await api('/api/processes/import', { method: 'POST', body: JSON.stringify(manual) });
    setManual({ process_id: '', city: '', process_type: 'Ejecutivo hipotecario', status_text: '' });
    setMessage('Proceso importado');
    await refresh();
    await events.refresh();
  }

  return (
    <main className="content-grid">
      <section className="band">
        <form className="toolbar" onSubmit={enqueue}>
          <label className="search-box">
            <Search size={18} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar proceso, ciudad o evento" />
          </label>
          <input value={radicado} onChange={(event) => setRadicado(event.target.value)} placeholder="Radicado" />
          <button className="primary-button"><Play size={17} /> Encolar</button>
          <button type="button" className="icon-button" onClick={refresh} title="Actualizar"><RefreshCcw size={17} /></button>
        </form>
        {message ? <div className="success-line">{message}</div> : null}
        <ProcessTable rows={data?.rows || []} loading={loading} />
      </section>
      <section className="band">
        <div className="section-title"><h3>Importacion operativa</h3></div>
        <form className="manual-form" onSubmit={importManual}>
          <input value={manual.process_id} onChange={(event) => setManual({ ...manual, process_id: event.target.value })} placeholder="Radicado" required />
          <input value={manual.city} onChange={(event) => setManual({ ...manual, city: event.target.value })} placeholder="Ciudad" />
          <input value={manual.process_type} onChange={(event) => setManual({ ...manual, process_type: event.target.value })} placeholder="Tipo de proceso" />
          <textarea value={manual.status_text} onChange={(event) => setManual({ ...manual, status_text: event.target.value })} placeholder="Actuacion o estado detectado" required />
          <button className="secondary-button"><Database size={17} /> Importar</button>
        </form>
      </section>
      <section className="band">
        <div className="section-title"><h3>Alertas</h3></div>
        <EventList rows={events.data?.rows || []} />
      </section>
    </main>
  );
}

function Queue() {
  const jobs = useLoad(() => api('/api/jobs'), []);
  const rate = useLoad(() => api('/api/rate-limit'), []);
  const [busy, setBusy] = useState(false);

  async function seed() {
    setBusy(true);
    await api('/api/jobs/demo-seed', { method: 'POST', body: JSON.stringify({ count: 10 }) });
    await jobs.refresh();
    setBusy(false);
  }

  async function tick() {
    setBusy(true);
    await api('/api/worker/tick', { method: 'POST' });
    await Promise.all([jobs.refresh(), rate.refresh()]);
    setBusy(false);
  }

  return (
    <main className="content-grid">
      <section className="band">
        <div className="toolbar">
          <button className="primary-button" onClick={seed} disabled={busy}><Database size={17} /> Demo</button>
          <button className="secondary-button" onClick={tick} disabled={busy}><Play size={17} /> Worker</button>
          <button className="icon-button" onClick={jobs.refresh} title="Actualizar"><RefreshCcw size={17} /></button>
        </div>
        <JobsTable rows={jobs.data?.rows || []} />
      </section>
      <section className="band">
        <div className="section-title"><h3>Limites de fuente</h3></div>
        <SimpleTable rows={rate.data?.rows || []} columns={['source_key', 'min_seconds_between_requests', 'daily_limit', 'requests_today', 'last_request_at']} />
      </section>
    </main>
  );
}

function Compliance() {
  const reviews = useLoad(() => api('/api/compliance/reviews'), []);
  const requests = useLoad(() => api('/api/compliance/requests'), []);
  const audit = useLoad(() => api('/api/audit'), []);
  return (
    <main className="content-grid">
      <section className="band two">
        <div>
          <div className="section-title"><h3>Revision legal</h3></div>
          <ReviewList rows={reviews.data?.rows || []} refresh={reviews.refresh} />
        </div>
        <RequestForm refresh={requests.refresh} />
      </section>
      <section className="band">
        <div className="section-title"><h3>Solicitudes titulares</h3></div>
        <SimpleTable rows={requests.data?.rows || []} columns={['request_type', 'requester_contact', 'related_process_id', 'status', 'created_at']} />
      </section>
      <section className="band">
        <div className="section-title"><h3>Auditoria</h3></div>
        <SimpleTable rows={audit.data?.rows || []} columns={['actor', 'action', 'entity_type', 'entity_id', 'created_at']} />
      </section>
    </main>
  );
}

function Business() {
  const { data, loading } = useLoad(() => api('/api/business/projection'), []);
  const clients = useLoad(() => api('/api/clients'), []);
  const [client, setClient] = useState({ name: '', email: '', plan: 'starter' });
  if (loading || !data) return <Loading />;
  const rows = Object.entries(data.baseline).map(([plan, item]) => ({
    plan,
    clients: item.clients,
    price: money(item.price),
    revenue: money(item.clients * item.price)
  }));
  async function saveClient(event) {
    event.preventDefault();
    await api('/api/clients', { method: 'POST', body: JSON.stringify(client) });
    setClient({ name: '', email: '', plan: 'starter' });
    await clients.refresh();
  }
  return (
    <main className="content-grid">
      <div className="metric-grid compact-metrics">
        <div className="metric"><BriefcaseBusiness size={20} /><span>MRR actual</span><strong>{money(data.currentMonthly)}</strong></div>
        <div className="metric"><Activity size={20} /><span>Meta inicial</span><strong>{money(data.projectedMonthly)}</strong></div>
      </div>
      <section className="band">
        <div className="section-title"><h3>Escenario 20-50M COP</h3></div>
        <SimpleTable rows={rows} columns={['plan', 'clients', 'price', 'revenue']} />
      </section>
      <section className="band two">
        <form className="request-form" onSubmit={saveClient}>
          <div className="section-title"><h3>Nuevo cliente</h3></div>
          <input value={client.name} onChange={(event) => setClient({ ...client, name: event.target.value })} placeholder="Nombre" required />
          <input value={client.email} onChange={(event) => setClient({ ...client, email: event.target.value })} placeholder="Email" type="email" required />
          <select value={client.plan} onChange={(event) => setClient({ ...client, plan: event.target.value })}>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="enterprise">Enterprise</option>
          </select>
          <button className="secondary-button"><Users size={17} /> Guardar</button>
        </form>
        <div>
          <div className="section-title"><h3>Clientes activos</h3></div>
          <SimpleTable rows={clients.data?.rows || []} columns={['name', 'email', 'plan', 'status', 'monthly_price_cop']} />
        </div>
      </section>
    </main>
  );
}

function Deploy() {
  const { data, loading } = useLoad(() => api('/api/deploy/hostinger'), []);
  if (loading || !data) return <Loading />;
  return (
    <main className="content-grid">
      <section className="band">
        <div className="section-title"><h3>Hostinger Cloud Startup</h3></div>
        <div className="deploy-grid">
          <CodeBlock title="Build" value={data.buildCommand} />
          <CodeBlock title="Start" value={data.startCommand} />
          <CodeBlock title="Runtime" value={data.runtime} />
          <CodeBlock title="Salida" value={data.documentRoot} />
        </div>
      </section>
      <section className="band">
        <div className="section-title"><h3>Variables</h3></div>
        <div className="env-grid">
          {data.variables.map((item) => <span key={item}>{item}</span>)}
        </div>
      </section>
    </main>
  );
}

function CodeBlock({ title, value }) {
  return <div className="code-block"><span>{title}</span><code>{value}</code></div>;
}

function ProcessTable({ rows, loading }) {
  if (loading) return <Loading />;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Radicado</th><th>Ciudad</th><th>Tipo</th><th>Riesgo</th><th>Estado</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="mono">{row.process_id}</td>
              <td>{row.city || '-'}</td>
              <td>{row.process_type || '-'}</td>
              <td><span className={Number(row.risk_score) >= 15 ? 'risk high' : 'risk'}>{row.risk_score}</span></td>
              <td className="clip">{row.current_status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobsTable({ rows }) {
  return <SimpleTable rows={rows} columns={['id', 'lookup_key', 'status', 'attempts', 'run_after', 'last_error']} />;
}

function SimpleTable({ rows, columns }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={row.id || idx}>
              {columns.map((column) => <td key={column} className={column.includes('id') || column.includes('key') ? 'mono' : ''}>{String(row[column] ?? '-')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EventList({ rows }) {
  if (!rows?.length) return <div className="empty">Sin eventos registrados</div>;
  return (
    <div className="event-list">
      {rows.map((row) => (
        <article key={row.id} className="event-card">
          <span className={Number(row.severity) >= 8 ? 'severity urgent' : 'severity'}>{row.severity}</span>
          <div>
            <strong>{row.event_type}</strong>
            <p>{row.excerpt}</p>
            <small>{row.process_id}</small>
          </div>
        </article>
      ))}
    </div>
  );
}

function ReviewList({ rows, refresh }) {
  async function close(id) {
    await api(`/api/compliance/reviews/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'closed', owner: 'admin' }) });
    refresh();
  }
  return (
    <div className="review-list">
      {rows.map((row) => (
        <article key={row.id} className="review-item">
          <span className={`severity ${row.severity}`}>{row.severity}</span>
          <div>
            <strong>{row.title}</strong>
            <p>{row.description}</p>
          </div>
          {row.status !== 'closed' ? <button className="icon-button" onClick={() => close(row.id)} title="Cerrar"><CheckCircle2 size={17} /></button> : null}
        </article>
      ))}
    </div>
  );
}

function RequestForm({ refresh }) {
  const [contact, setContact] = useState('');
  async function submit(event) {
    event.preventDefault();
    await api('/api/compliance/requests', {
      method: 'POST',
      body: JSON.stringify({ request_type: 'claim', requester_contact: contact, notes: 'Registro desde dashboard' })
    });
    setContact('');
    refresh();
  }
  return (
    <form className="request-form" onSubmit={submit}>
      <div className="section-title"><h3>Nuevo reclamo</h3></div>
      <input value={contact} onChange={(event) => setContact(event.target.value)} placeholder="correo o telefono" required />
      <button className="secondary-button"><ShieldCheck size={17} /> Registrar</button>
    </form>
  );
}

function Loading() {
  return <div className="loading"><RefreshCcw size={18} /> Cargando</div>;
}

createRoot(document.getElementById('root')).render(<App />);
