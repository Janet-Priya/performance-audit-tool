import React, { useState, useEffect } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from 'recharts';
import './App.css';

/**
 * Manager API base:
 * - REACT_APP_API_URL if set (explicit base URL).
 * - Development (`npm start`): http://127.0.0.1:8001 (CORS on manager).
 * - Production build without REACT_APP_API_URL: same-origin `/api/...` (use nginx or another reverse proxy — see Docker).
 * Set REACT_APP_API_URL when serving a static build without a proxy (e.g. http://127.0.0.1:8001).
 */
const REACT_API_BASE = (process.env.REACT_APP_API_URL || '').replace(/\/$/, '');
const MANAGER_ORIGIN = 'http://127.0.0.1:8001';
/** Base URL of the service under test (browser → manager → target). Use http://target-api:8000 when both run in Docker Compose. */
const DEFAULT_TARGET_URL = (process.env.REACT_APP_TARGET_URL || 'http://localhost:8000').replace(/\/$/, '');
const apiUrl = (path) => {
  const p = path.startsWith('/') ? path : `/${path}`;
  if (REACT_API_BASE) return `${REACT_API_BASE}${p}`;
  if (process.env.NODE_ENV === 'development') return `${MANAGER_ORIGIN}${p}`;
  return p;
};

/** For user-facing hints: where the UI expects the API (direct URL, or same-origin in Docker/nginx). */
const managerHintUrl = () => {
  if (REACT_API_BASE) return REACT_API_BASE;
  if (process.env.NODE_ENV === 'development') return MANAGER_ORIGIN;
  if (typeof window !== 'undefined' && window.location?.origin) {
    return `${window.location.origin} (paths under /api)`;
  }
  return MANAGER_ORIGIN;
};

const sampleHistoryUrl = () => {
  if (REACT_API_BASE) return `${REACT_API_BASE}/api/tests/history`;
  if (process.env.NODE_ENV === 'development') return `${MANAGER_ORIGIN}/api/tests/history`;
  if (typeof window !== 'undefined' && window.location?.origin) {
    return `${window.location.origin}/api/tests/history`;
  }
  return `${MANAGER_ORIGIN}/api/tests/history`;
};

const apiHeaders = () => {
  const h = {};
  const k = process.env.REACT_APP_AUDIT_API_KEY;
  if (k) h['X-API-Key'] = k;
  return h;
};

const formatTs = (ts) => {
  if (!ts) return '—';
  const s = String(ts);
  return s.length >= 19 ? s.slice(0, 19).replace('T', ' ') : s;
};

const ENDPOINTS = ['/health', '/login', '/get-data', '/users', '/upload', '/search', '/notifications'];
const METHODS = {
  '/health': 'GET',
  '/login': 'POST',
  '/get-data': 'GET',
  '/users': 'GET',
  '/upload': 'POST',
  '/search': 'GET',
  '/notifications': 'GET',
};

const statusClass = (status) => {
  if (status === 'PASS') return 'status-pill status-pill--pass';
  if (status === 'WARN') return 'status-pill status-pill--warn';
  if (status === 'FAIL') return 'status-pill status-pill--fail';
  return 'status-pill status-pill--neutral';
};

export default function App() {
  const [history, setHistory] = useState([]);
  const [selectedTest, setSelectedTest] = useState(null);
  const [config, setConfig] = useState({
    endpoint: '/login',
    total_requests: 100,
    concurrency: 10,
    load_profile: 'flat',
    ramp_peak_concurrency: 24,
    ramp_steps: 5,
  });
  const [running, setRunning] = useState(false);
  const [runProgress, setRunProgress] = useState(null);
  const [error, setError] = useState('');
  const [managerHealth, setManagerHealth] = useState({ ok: true, message: '' });
  const [intelligence, setIntelligence] = useState(null);
  const [baselines, setBaselines] = useState([]);
  const [historyFilter, setHistoryFilter] = useState({ q: '', status: '', from_ts: '', to_ts: '' });
  const [historyPage, setHistoryPage] = useState(0);
  const [historyTotal, setHistoryTotal] = useState(0);
  const historyLimit = 50;
  /** Latest runs for the chart only (ignores table filters/pagination). */
  const [trendHistory, setTrendHistory] = useState([]);
  const [brand, setBrand] = useState({
    app_title: 'Performance audit',
    app_subtitle: 'Load testing and latency insights',
  });

  const fetchHistory = async (pageOverride) => {
    const page = pageOverride !== undefined ? pageOverride : historyPage;
    try {
      const params = new URLSearchParams();
      params.set('limit', String(historyLimit));
      params.set('offset', String(page * historyLimit));
      if (historyFilter.q.trim()) params.set('q', historyFilter.q.trim());
      if (historyFilter.status.trim()) params.set('status', historyFilter.status.trim());
      if (historyFilter.from_ts.trim()) params.set('from_ts', historyFilter.from_ts.trim());
      if (historyFilter.to_ts.trim()) params.set('to_ts', historyFilter.to_ts.trim());
      const res = await fetch(apiUrl(`/api/tests/history?${params}`), { headers: apiHeaders() });
      if (!res.ok) {
        setError(
          `Manager API returned ${res.status}. Open ${sampleHistoryUrl()} in a new tab (should be JSON). Start the manager: see README (Docker: docker compose up --build; local: uvicorn in manager-api on port 8001).`
        );
        return;
      }
      const data = await res.json();
      const items = data.items ?? data;
      setHistory(Array.isArray(items) ? items : []);
      setHistoryTotal(typeof data.total === 'number' ? data.total : items.length);
      setError('');
    } catch (e) {
      const hint = e?.message ? ` (${e.message})` : '';
      setError(
        `Cannot reach the manager (${managerHintUrl()})${hint}. Start it: from repo root run docker compose up --build, or cd manager-api && uvicorn main:app --host 127.0.0.1 --port 8001 — then reload this page.`
      );
    }
  };

  const fetchTrendHistory = async () => {
    try {
      const params = new URLSearchParams();
      params.set('limit', '15');
      params.set('offset', '0');
      const res = await fetch(apiUrl(`/api/tests/history?${params}`), { headers: apiHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      const items = data.items ?? [];
      setTrendHistory(Array.isArray(items) ? items : []);
    } catch (_) {
      setTrendHistory([]);
    }
  };

  const fetchBaselines = async () => {
    try {
      const res = await fetch(apiUrl('/api/baselines'), { headers: apiHeaders() });
      if (res.ok) setBaselines(await res.json());
    } catch (_) {
      setBaselines([]);
    }
  };

  useEffect(() => {
    fetchHistory();
    fetchTrendHistory();
    fetchBaselines();
    (async () => {
      try {
        const res = await fetch(apiUrl('/api/settings'), { headers: apiHeaders() });
        if (res.ok) {
          const s = await res.json();
          setBrand({
            app_title: s.app_title || 'Performance audit',
            app_subtitle: s.app_subtitle || '',
          });
          if (typeof document !== 'undefined') {
            document.title = s.app_title || 'Latency audit';
          }
        }
      } catch (_) {
        /* keep defaults */
      }
    })();
  }, []);

  useEffect(() => {
    const tick = async () => {
      try {
        const res = await fetch(apiUrl('/api/health'), { headers: apiHeaders() });
        if (res.ok) {
          setManagerHealth({ ok: true, message: '' });
        } else {
          const t = await res.text();
          setManagerHealth({ ok: false, message: `HTTP ${res.status} ${t.slice(0, 120)}` });
        }
      } catch (e) {
        setManagerHealth({ ok: false, message: e?.message || 'Unreachable' });
      }
    };
    tick();
    const id = setInterval(tick, 8000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (history.length > 0 && selectedTest == null) {
      setSelectedTest(history[0].test_id);
    }
  }, [history, selectedTest]);

  const fetchIntelligence = async (testId) => {
    if (!testId) {
      setIntelligence(null);
      return;
    }
    try {
      const res = await fetch(apiUrl(`/api/tests/${testId}/intelligence`), { headers: apiHeaders() });
      if (res.ok) {
        const data = await res.json();
        setIntelligence(data);
      }
    } catch (_) {
      setIntelligence(null);
    }
  };

  useEffect(() => {
    if (selectedTest) fetchIntelligence(selectedTest);
  }, [selectedTest]);

  const runTest = async () => {
    setRunning(true);
    setError('');
    const totalReq = parseInt(config.total_requests, 10);
    setRunProgress({ done: 0, total: Math.max(1, totalReq) });
    const ramp = config.load_profile === 'ramp';
    try {
      const res = await fetch(apiUrl('/api/tests/run'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...apiHeaders() },
        body: JSON.stringify({
          target_url: DEFAULT_TARGET_URL,
          endpoint: config.endpoint,
          method: METHODS[config.endpoint] || 'GET',
          total_requests: totalReq,
          concurrency: parseInt(config.concurrency, 10),
          load_profile: config.load_profile,
          ramp_peak_concurrency: ramp ? parseInt(config.ramp_peak_concurrency, 10) : null,
          ramp_steps: ramp ? parseInt(config.ramp_steps, 10) : 5,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = body.detail;
        let msg = `Request failed (${res.status})`;
        if (typeof detail === 'string') msg = detail;
        else if (Array.isArray(detail)) msg = detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
        else if (detail && typeof detail === 'object') msg = JSON.stringify(detail);
        setError(msg);
        setRunProgress(null);
        setRunning(false);
        return;
      }
      const { job_id: jobId } = body;
      if (!jobId) {
        setError('No job_id from server');
        setRunProgress(null);
        setRunning(false);
        return;
      }
      const result = await new Promise((resolve, reject) => {
        const poll = async () => {
          try {
            const r = await fetch(apiUrl(`/api/tests/jobs/${jobId}`), { headers: apiHeaders() });
            const j = await r.json();
            setRunProgress({
              done: j.progress ?? 0,
              total: Math.max(1, j.total ?? totalReq),
            });
            if (j.status === 'completed' && j.result) {
              resolve(j.result);
            } else if (j.status === 'failed') {
              reject(new Error(j.error || 'Load test failed'));
            } else {
              setTimeout(poll, 450);
            }
          } catch (e) {
            reject(e);
          }
        };
        poll();
      });
      await fetchHistory(0);
      await fetchTrendHistory();
      setHistoryPage(0);
      setSelectedTest(result.test_id);
      if (result.intelligence) setIntelligence(result.intelligence);
    } catch (e) {
      setError('Test failed: ' + e.message);
    }
    setRunning(false);
    setRunProgress(null);
  };

  const pinBaseline = async () => {
    if (!selectedTest) return;
    try {
      await fetch(apiUrl('/api/baselines'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...apiHeaders() },
        body: JSON.stringify({ test_id: selectedTest }),
      });
      await fetchBaselines();
      await fetchIntelligence(selectedTest);
    } catch (e) {
      setError('Could not pin baseline');
    }
  };

  const clearBaseline = async () => {
    const row = history.find((h) => h.test_id === selectedTest);
    if (!row?.endpoint_url) return;
    try {
      await fetch(apiUrl(`/api/baselines?endpoint_url=${encodeURIComponent(row.endpoint_url)}`), {
        method: 'DELETE',
        headers: apiHeaders(),
      });
      await fetchBaselines();
      await fetchIntelligence(selectedTest);
    } catch (e) {
      setError('Could not clear baseline');
    }
  };

  const openReport = (testId) => {
    const url = apiUrl(`/api/report/${testId}`);
    const w = window.open(url, '_blank', 'noopener,noreferrer');
    if (w == null) {
      window.location.assign(url);
    }
  };

  const downloadExport = async (ext) => {
    const path = `/api/export/history.${ext}`;
    const url = apiUrl(path);
    try {
      const res = await fetch(url, { method: 'GET', headers: apiHeaders() });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = `history.${ext}`;
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(href);
    } catch (_) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  const chartData = trendHistory
    .slice(0, 15)
    .reverse()
    .map((t, i) => ({
      name: `#${i + 1}`,
      avg: t.avg_latency,
      p99: t.p99_latency,
      endpoint: t.endpoint_url.split('/').pop(),
    }));

  const chartTooltip = {
    contentStyle: {
      background: 'rgba(12, 16, 24, 0.95)',
      border: '1px solid rgba(148, 163, 184, 0.15)',
      borderRadius: '10px',
      fontSize: '12px',
      boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
    },
    labelStyle: { color: '#94a3b8' },
  };

  const riskFill = (n) => {
    if (n >= 70) return '#dc2626';
    if (n >= 40) return '#d97706';
    return '#059669';
  };

  const selectedRow = history.find((h) => h.test_id === selectedTest);
  const baselineForUrl = baselines.find((b) => b.endpoint_url === selectedRow?.endpoint_url);

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-brand">
          <div className="app-logo" aria-hidden>
            P
          </div>
          <div>
            <h1 className="app-title">{brand.app_title}</h1>
            <p className="app-title-meta">{brand.app_subtitle}</p>
          </div>
        </div>
        <div className="header-actions">
          <div
            className={`manager-health ${managerHealth.ok ? 'manager-health--ok' : 'manager-health--bad'}`}
            title={managerHealth.ok ? 'Manager API reachable' : managerHealth.message}
          >
            <span className="manager-health-dot" aria-hidden />
            {managerHealth.ok ? 'Manager online' : 'Manager offline'}
          </div>
          <div className="export-links">
            <button type="button" className="export-btn" onClick={() => downloadExport('csv')}>
              CSV
            </button>
            <button type="button" className="export-btn" onClick={() => downloadExport('json')}>
              JSON
            </button>
          </div>
        </div>
      </header>

      {!managerHealth.ok && (
        <div className="error-banner error-banner--health">
          <strong>Cannot reach manager API.</strong> {managerHealth.message} — start the stack (see README):{' '}
          <code>docker compose up --build</code> or run <code>uvicorn</code> in manager-api on port 8001.
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}

      <div className="app-main">
        <aside>
          <details className="help-accordion">
            <summary>How to use this tool</summary>
            <div className="help-body">
              <ol>
                <li>
                  Start <strong>target-api</strong> (port 8000) and <strong>manager-api</strong> (8001), then this dashboard (3000).
                </li>
                <li>
                  Pick an endpoint, choose <strong>flat</strong> or <strong>ramp</strong> load, set requests and concurrency, then{' '}
                  <strong>Run audit</strong>.
                </li>
                <li>
                  Read <strong>Insights</strong> for the selected row (click a history row). Pin a <strong>baseline</strong> to
                  compare later runs.
                </li>
                <li>
                  <strong>Report</strong> opens a printable HTML summary for that run in a new tab — use the browser print dialog
                  (Ctrl/Cmd+P) to save PDF.
                </li>
              </ol>
            </div>
          </details>
          <section className="panel">
            <h2 className="panel-title">Run load test</h2>
            <label className="field-label" htmlFor="endpoint">
              Endpoint
            </label>
            <select
              id="endpoint"
              className="select"
              value={config.endpoint}
              onChange={(e) => setConfig({ ...config, endpoint: e.target.value })}
            >
              {ENDPOINTS.map((ep) => (
                <option key={ep} value={ep}>
                  {METHODS[ep]} {ep}
                </option>
              ))}
            </select>
            <label className="field-label" htmlFor="profile">
              Load shape
            </label>
            <select
              id="profile"
              className="select"
              value={config.load_profile}
              onChange={(e) => setConfig({ ...config, load_profile: e.target.value })}
            >
              <option value="flat">Flat (fixed concurrency)</option>
              <option value="ramp">Ramp (phases increase concurrency)</option>
            </select>
            <label className="field-label" htmlFor="req">
              Requests
            </label>
            <input
              id="req"
              className="input"
              type="number"
              value={config.total_requests}
              onChange={(e) => setConfig({ ...config, total_requests: e.target.value })}
              min="10"
              max="500"
            />
            <label className="field-label" htmlFor="conc">
              Concurrency {config.load_profile === 'ramp' ? '(start cap)' : ''}
            </label>
            <input
              id="conc"
              className="input"
              type="number"
              value={config.concurrency}
              onChange={(e) => setConfig({ ...config, concurrency: e.target.value })}
              min="1"
              max="50"
            />
            {config.load_profile === 'ramp' && (
              <>
                <label className="field-label" htmlFor="rpeak">
                  Ramp peak concurrency
                </label>
                <input
                  id="rpeak"
                  className="input"
                  type="number"
                  value={config.ramp_peak_concurrency}
                  onChange={(e) => setConfig({ ...config, ramp_peak_concurrency: e.target.value })}
                  min="2"
                  max="80"
                />
                <label className="field-label" htmlFor="rsteps">
                  Ramp steps
                </label>
                <input
                  id="rsteps"
                  className="input"
                  type="number"
                  value={config.ramp_steps}
                  onChange={(e) => setConfig({ ...config, ramp_steps: e.target.value })}
                  min="2"
                  max="20"
                />
              </>
            )}
            <button className="btn-primary" type="button" onClick={runTest} disabled={running}>
              {running ? 'Running…' : 'Run audit'}
            </button>
            {runProgress && running && (
              <div className="run-progress" aria-live="polite">
                <div className="run-progress-bar">
                  <div
                    className="run-progress-fill"
                    style={{
                      width: `${Math.min(100, (100 * runProgress.done) / Math.max(1, runProgress.total))}%`,
                    }}
                  />
                </div>
                <span className="run-progress-label">
                  {runProgress.done} / {runProgress.total} requests
                </span>
              </div>
            )}
          </section>

          <section className="panel">
            <h2 className="panel-title">SLA (avg latency)</h2>
            <ul className="sla-list">
              <li>
                <span className="sla-name">Pass</span>
                <span className="sla-desc">&lt; 200 ms</span>
              </li>
              <li>
                <span className="sla-name">Warn</span>
                <span className="sla-desc">200–500 ms</span>
              </li>
              <li>
                <span className="sla-name">Fail</span>
                <span className="sla-desc">&gt; 500 ms</span>
              </li>
            </ul>
            <p className="hint" style={{ marginTop: '12px' }}>
              SLO panel in insights uses P99 ≤ 400 ms and errors ≤ 2% over a rolling window (approximate error-budget view).
            </p>
          </section>
        </aside>

        <div className="stack">
          <section className="panel">
            <div className="chart-card-head">
              <h2 className="panel-title" style={{ marginBottom: 0 }}>
                Latency trend
              </h2>
              <span className="chart-badge">Last 15 runs</span>
            </div>
            <p className="hint">
              Dashed line: estimated next P99 for the selected row’s endpoint. Ramp mode ramps concurrency in steps (see History →
              Mode).
            </p>
            {chartData.length === 0 ? (
              <div className="chart-empty">No runs yet. Start one from the left.</div>
            ) : (
              <ResponsiveContainer width="100%" height={228}>
                <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" vertical={false} />
                  <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 11 }} tickLine={false} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 11 }} tickLine={false} unit=" ms" width={44} />
                  <Tooltip {...chartTooltip} />
                  <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }} />
                  <Line
                    type="monotone"
                    dataKey="avg"
                    name="Avg"
                    stroke="#38bdf8"
                    strokeWidth={1.75}
                    dot={false}
                    activeDot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="p99"
                    name="P99"
                    stroke="#fb923c"
                    strokeWidth={1.75}
                    strokeDasharray="4 3"
                    dot={false}
                    activeDot={{ r: 3 }}
                  />
                  {intelligence &&
                    intelligence.forecast &&
                    intelligence.forecast.usable &&
                    intelligence.forecast.next_p99_ms != null && (
                      <ReferenceLine
                        y={intelligence.forecast.next_p99_ms}
                        stroke="#eab308"
                        strokeDasharray="5 4"
                        strokeOpacity={0.9}
                        label={{
                          value: 'Next P99 (est.)',
                          fill: '#ca8a04',
                          fontSize: 11,
                          position: 'insideTopRight',
                        }}
                      />
                    )}
                </LineChart>
              </ResponsiveContainer>
            )}
          </section>

          {intelligence && intelligence.anomaly && (
            <section className="panel">
              <h2 className="panel-title">Insights · selected run</h2>
              <p className="intel-footnote">
                Isolation forest vs recent history, linear P99 trend, approximate SLO budget, regression vs pinned baseline, and a static dependency map for blast-radius context.
              </p>
              <div className="toolbar-row">
                <button type="button" className="btn-ghost" onClick={pinBaseline}>
                  Pin selected as baseline
                </button>
                <button type="button" className="btn-ghost" onClick={clearBaseline}>
                  Clear baseline for this URL
                </button>
              </div>
              {baselineForUrl && baselineForUrl.baseline_snapshot && (
                <p className="baseline-hint">
                  Comparing to baseline run from <strong>{formatTs(baselineForUrl.baseline_snapshot.timestamp)}</strong> (avg{' '}
                  {baselineForUrl.baseline_snapshot.avg_latency} ms · P99 {baselineForUrl.baseline_snapshot.p99_latency} ms).
                </p>
              )}
              {intelligence.ai_summary && (
                <div className="intel-block ai-summary-block">
                  <span className="field-label">AI summary</span>
                  <p className="ai-summary-headline">{intelligence.ai_summary.headline}</p>
                  <p className="mono-sm">
                    Confidence ~{(intelligence.ai_summary.confidence * 100).toFixed(0)}% · {intelligence.ai_summary.history_points}{' '}
                    history point(s). {intelligence.ai_summary.hint}
                  </p>
                </div>
              )}
              <div className="insights-grid">
                <div>
                  <span className="field-label">Risk index (0–100)</span>
                  <div className="risk-track">
                    <div
                      className="risk-fill"
                      style={{
                        width: `${intelligence.composite_risk}%`,
                        background: riskFill(intelligence.composite_risk),
                      }}
                    />
                  </div>
                  <div className="risk-num">{intelligence.composite_risk}</div>
                </div>
                <div>
                  <span className="field-label">Vs recent baseline</span>
                  <div>
                    <span
                      className={
                        intelligence.anomaly.is_anomaly
                          ? 'anomaly-pill anomaly-pill--bad'
                          : 'anomaly-pill anomaly-pill--ok'
                      }
                    >
                      {intelligence.anomaly.is_anomaly ? 'Unusual' : 'Typical'}
                    </span>
                  </div>
                  <div className="forecast-meta" style={{ marginTop: '8px' }}>
                    {String(intelligence.anomaly.method).replace(/_/g, ' ')} · n = {intelligence.anomaly.history_runs}
                    {intelligence.anomaly.score != null && ` · ${intelligence.anomaly.score}`}
                  </div>
                </div>
                <div>
                  <span className="field-label">Next P99 (estimate)</span>
                  {intelligence.forecast && intelligence.forecast.usable ? (
                    <>
                      <div className="forecast-value">~{intelligence.forecast.next_p99_ms} ms</div>
                      <div className="forecast-meta">
                        {intelligence.forecast.slope_ms_per_run} ms per run · residual σ ≈ {intelligence.forecast.stderr_hint}{' '}
                        ms
                      </div>
                    </>
                  ) : (
                    <div className="forecast-meta" style={{ marginTop: '4px' }}>
                      Run this endpoint a few more times to estimate a trend.
                    </div>
                  )}
                </div>
              </div>

              {intelligence.slo && (
                <div className="intel-block">
                  <span className="field-label">SLO / error budget (approx.)</span>
                  <div className="kv">
                    <div>
                      Targets: P99 ≤ {intelligence.slo.targets?.p99_ms} ms, errors ≤ {intelligence.slo.targets?.max_error_pct}%
                    </div>
                    <div>
                      <strong>{intelligence.slo.current_meets_slo ? 'Meets' : 'Violates'}</strong> SLO on this run.
                    </div>
                    {intelligence.slo.error_budget_remaining_pct != null && (
                      <div>
                        Budget remaining (rolling window): <strong>{intelligence.slo.error_budget_remaining_pct}%</strong>
                      </div>
                    )}
                    {intelligence.slo.burn_rate != null && (
                      <div>
                        Burn rate (later vs earlier half of window): <strong>{intelligence.slo.burn_rate}</strong>
                        {intelligence.slo.burn_rate > 0 ? ' (worsening)' : ''}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {intelligence.regression && (
                <div className="intel-block">
                  <span className="field-label">Regression vs pinned baseline</span>
                  {intelligence.regression.has_baseline ? (
                    <div className="kv">
                      <div>
                        Δ P99: <strong>{intelligence.regression.delta_p99_ms} ms</strong> · Δ avg:{' '}
                        <strong>{intelligence.regression.delta_avg_ms} ms</strong> · Δ errors:{' '}
                        <strong>{intelligence.regression.delta_error_rate_pct}</strong> pts
                      </div>
                      <div>
                        Severity: <strong>{intelligence.regression.regression_severity}</strong>
                      </div>
                    </div>
                  ) : (
                    <div className="kv">Pin a baseline run to compare.</div>
                  )}
                </div>
              )}

              {intelligence.diagnostics && (
                <div className="intel-block">
                  <span className="field-label">Multi-signal pattern</span>
                  <div className="kv">
                    Label: <strong>{intelligence.diagnostics.pattern}</strong> · spread {intelligence.diagnostics.signals?.spread_ms}{' '}
                    ms
                  </div>
                  <ul className="insights-list">
                    {(intelligence.diagnostics.hints || []).map((h, i) => (
                      <li key={i}>{h}</li>
                    ))}
                  </ul>
                </div>
              )}

              {intelligence.dependencies && (
                <div className="intel-block">
                  <span className="field-label">Dependency blast radius (demo)</span>
                  <div className="kv">
                    Path <strong>{intelligence.dependencies.path}</strong>
                  </div>
                  <div className="kv">
                    Upstream: {intelligence.dependencies.upstream?.length ? intelligence.dependencies.upstream.join(', ') : '—'}
                  </div>
                  <div className="kv">
                    Downstream:{' '}
                    {intelligence.dependencies.downstream?.length ? intelligence.dependencies.downstream.join(', ') : '—'}
                  </div>
                  <p className="mono-sm">{intelligence.dependencies.note}</p>
                </div>
              )}

              {intelligence.explainability && (
                <div className="intel-block">
                  <span className="field-label">Which features look most off (scaled)</span>
                  <p className="mono-sm">{intelligence.explainability.method}</p>
                  {(intelligence.explainability.top_features || []).map((f, i) => (
                    <div key={i} className="explain-row">
                      <span>{f.feature}</span>
                      <span>{f.scaled_abs_deviation}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="intel-block">
                <span className="field-label">Notes</span>
                <ul className="insights-list">
                  {(intelligence.recommendations || []).map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </div>
            </section>
          )}

          <section className="panel">
            <div className="panel-head">
              <h2 className="panel-title" style={{ marginBottom: 0 }}>
                History
              </h2>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  fetchHistory(historyPage);
                  fetchTrendHistory();
                }}
              >
                Refresh
              </button>
            </div>
            <div className="history-filters">
              <input
                type="search"
                className="input input--sm"
                placeholder="Search path, method, run id…"
                value={historyFilter.q}
                onChange={(e) => setHistoryFilter({ ...historyFilter, q: e.target.value })}
                aria-label="Filter history"
              />
              <select
                className="select select--sm"
                value={historyFilter.status}
                onChange={(e) => setHistoryFilter({ ...historyFilter, status: e.target.value })}
                aria-label="SLA status"
              >
                <option value="">All SLA</option>
                <option value="PASS">PASS</option>
                <option value="WARN">WARN</option>
                <option value="FAIL">FAIL</option>
              </select>
              <input
                type="datetime-local"
                className="input input--sm"
                value={historyFilter.from_ts}
                onChange={(e) => setHistoryFilter({ ...historyFilter, from_ts: e.target.value })}
                aria-label="From time"
              />
              <input
                type="datetime-local"
                className="input input--sm"
                value={historyFilter.to_ts}
                onChange={(e) => setHistoryFilter({ ...historyFilter, to_ts: e.target.value })}
                aria-label="To time"
              />
              <button
                type="button"
                className="btn-ghost btn-ghost--sm"
                onClick={() => {
                  setHistoryPage(0);
                  fetchHistory(0);
                }}
              >
                Apply filters
              </button>
            </div>
            <div className="history-pager">
              <span className="mono-sm">
                {historyTotal === 0
                  ? '0 of 0'
                  : `${historyPage * historyLimit + 1}–${Math.min(historyTotal, (historyPage + 1) * historyLimit)} of ${historyTotal}`}
              </span>
              <button
                type="button"
                className="btn-ghost btn-ghost--sm"
                disabled={historyPage <= 0}
                onClick={() => {
                  const p = historyPage - 1;
                  setHistoryPage(p);
                  fetchHistory(p);
                }}
              >
                Prev
              </button>
              <button
                type="button"
                className="btn-ghost btn-ghost--sm"
                disabled={(historyPage + 1) * historyLimit >= historyTotal}
                onClick={() => {
                  const p = historyPage + 1;
                  setHistoryPage(p);
                  fetchHistory(p);
                }}
              >
                Next
              </button>
            </div>
            {history.length === 0 ? (
              <div className="chart-empty">Nothing logged yet.</div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Endpoint</th>
                      <th>Mode</th>
                      <th>Req</th>
                      <th>Wall s</th>
                      <th>Avg</th>
                      <th>P99</th>
                      <th>OK</th>
                      <th>RPS</th>
                      <th>SLA</th>
                      <th>Report</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((test) => {
                      const isSelected = test.test_id === selectedTest;
                      return (
                        <tr
                          key={test.test_id}
                          className={isSelected ? 'selected' : ''}
                          onClick={() => setSelectedTest(test.test_id)}
                        >
                          <td>
                            <span className="method-tag">{test.method}</span>
                            {test.endpoint_url
                            .replace(/^https?:\/\/localhost:8000/, '')
                            .replace(/^https?:\/\/target-api:8000/, '')}
                          </td>
                          <td className="mono-sm">{test.load_profile || 'flat'}</td>
                          <td>{test.total_requests}</td>
                          <td>{test.wall_duration_sec != null ? test.wall_duration_sec : '—'}</td>
                          <td>{test.avg_latency}</td>
                          <td>{test.p99_latency}</td>
                          <td style={{ color: '#94a3b8' }}>{test.success_rate}%</td>
                          <td>{test.throughput_rps}</td>
                          <td>
                            <span className={statusClass(test.status)}>{test.status}</span>
                          </td>
                          <td>
                            <button
                              type="button"
                              className="btn-inline"
                              onClick={(e) => {
                                e.stopPropagation();
                                openReport(test.test_id);
                              }}
                            >
                              Report
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
