# Performance audit tool

## Concept

This project is a **small performance-auditing stack** for HTTP APIs:

1. **Load generation** — The manager fires concurrent requests (async) against a target URL and records latency distributions (avg, percentiles), errors, and throughput.
2. **Persistence** — Each run is stored in SQLite so you can compare over time.
3. **Thresholds** — Simple SLA-style bands (e.g. pass/warn/fail on average latency) give an immediate signal.
4. **Intelligence layer** — On the server, scikit-learn models score each run against *recent history for the same endpoint* (anomaly detection + simple P99 trend). Rule-based SLO and diagnostics add context; a static dependency map is demo-only.
5. **Reporting** — A printable HTML page summarizes one run for sharing or archiving.

It is **not** a full APM or production observability platform; it is a focused tool for **repeatable load tests**, **trend visibility**, and **lightweight ML-assisted** anomaly hints.

---

Load testing and latency analysis for HTTP endpoints: async load generator (manager API), SQLite history, React dashboard, optional ramp profiles, SLO-style metrics, baseline comparison, and ML-based anomaly scoring.

---

## Quick setup (do this first)

You need **Python 3** + **pip**, and **Node.js** + **npm** (for the dashboard). Use **three separate terminal windows**.

| Step | Terminal | Folder | Command |
|------|-----------|--------|---------|
| **1** | Terminal A | `performance-audit-tool/target-api` | `pip install -r requirements.txt` then `uvicorn main:app --host 127.0.0.1 --port 8000 --reload` |
| **2** | Terminal B | `performance-audit-tool/manager-api` | `pip install -r requirements.txt` then `uvicorn main:app --host 127.0.0.1 --port 8001 --reload` |
| **3** | Terminal C | `performance-audit-tool/dashboard` | `npm install` (first time only) then `npm start` |

Then open **http://localhost:3000** in your browser. The UI talks to the **manager** (8001); the manager sends traffic to the **target API** (8000).

**Check it’s alive**

- Target: `http://127.0.0.1:8000/health` should return JSON.
- Manager: `http://127.0.0.1:8001/` should return JSON (not `Not Found`). Use **`127.0.0.1`** (with `.1`).
- API explorer: `http://127.0.0.1:8001/docs`.

**If a port is busy:** stop the old process or use `fuser -k 8001/tcp` (Linux) then start uvicorn again.

**Optional:** copy `.env.example` → `.env` in `manager-api` or `dashboard` only if you change URLs or branding (see Configuration below).

---

## How to run (three terminals)

### 1 — Target API (port 8000)

```bash
cd target-api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2 — Manager API (port 8001)

```bash
cd manager-api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Use **`http://127.0.0.1:8001/`** (note: `127.0.0.1`, not `127.0.0`) for a small JSON index, or **`http://127.0.0.1:8001/docs`** for interactive API docs. Data routes live under **`/api/...`**.

Optional: copy `manager-api/.env.example` to `.env` and set variables (see below).

### 3 — Dashboard (port 3000)

```bash
cd dashboard
npm install
npm start
```

During **`npm start`**, the UI calls the manager **directly** at **`http://127.0.0.1:8001`** (CORS allows `http://localhost:3000` and `http://127.0.0.1:3000`). The manager must be running before you open the dashboard.

For a **production build** (`npm run build`), set **`REACT_APP_API_URL`** in `.env` to your manager URL (or serve the UI behind a reverse proxy that forwards `/api`).

Open **http://localhost:3000**

---

## Configuration (no hardcoded branding)

**Manager API** serves `GET /api/settings` with title/subtitle/footer strings. Defaults are generic; override with environment variables:

| Variable | Purpose |
|----------|---------|
| `AUDIT_APP_TITLE` | Dashboard title (and base for report H1 unless `AUDIT_REPORT_TITLE` is set) |
| `AUDIT_APP_SUBTITLE` | Dashboard subtitle |
| `AUDIT_REPORT_TITLE` | HTML report main heading |
| `AUDIT_REPORT_SUBTITLE` | Extra line under the report heading (optional) |
| `AUDIT_REPORT_FOOTER` | Report footer text |
| `AUDIT_API_TITLE` | FastAPI OpenAPI title |
| `AUDIT_CORS_ORIGINS` | Comma-separated allowed origins (default includes `http://localhost:3000` and `http://127.0.0.1:3000`) |

The React app loads `/api/settings` on startup so labels stay in sync with the server.

---

## Where the ML runs

All **machine learning is server-side** in **`manager-api/intelligence.py`** (scikit-learn):

- **IsolationForest** on scaled multivariate features per endpoint (with a **modified Z / MAD** fallback when history is short).
- **LinearRegression** on run index vs P99 for a simple next-step forecast.
- **Feature “explainability”**: scaled distance from the training centroid per dimension.

Results are attached to **`POST /api/tests/run`** and **`GET /api/tests/{id}/intelligence`**. Heuristic SLO/diagnostics live in `slo.py` and `diagnostics.py` (rule-based, not neural nets).

---

## Operating the UI

1. Start all three processes (target, manager, dashboard).
2. Choose endpoint, load shape, requests, concurrency → **Run audit**.
3. Select a **History** row for insights; **Pin baseline** to compare later runs.
4. **Report** opens the HTML report (print to PDF from the browser if needed).
5. **CSV** / **JSON** in the header download full history.

---

## Project layout

```
performance-audit-tool/
├── target-api/          # Sample service under test
├── manager-api/         # FastAPI, SQLite, load engine, intelligence/
├── dashboard/           # React UI
└── README.md
```
