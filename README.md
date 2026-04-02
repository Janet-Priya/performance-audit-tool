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
| `AUDIT_DB_PATH` | SQLite file path (default `results.db` in the manager working directory). |
| `AUDIT_API_KEY` | If set, clients must send header `X-API-Key` for load tests and baseline pin/clear. |
| `AUDIT_ALLOWED_TARGET_HOSTS` | Optional comma-separated hostnames allowed in `target_url` (empty = no restriction). |
| `AUDIT_RATE_LIMIT_PER_MINUTE` | Per-IP cap on `POST /api/tests/run` (default `30`, use `0` to disable). |
| `AUDIT_REPLACE_LOCALHOST_TARGET` | **Docker:** rewrite `http://localhost:8000` / `127.0.0.1:8000` to this base (e.g. `http://target-api:8000`) so load tests hit the real target, not the manager container. |

The React app loads `/api/settings` on startup so labels stay in sync with the server.

**Dashboard `.env`:** `REACT_APP_API_URL` (manager base URL for production builds) and optional `REACT_APP_AUDIT_API_KEY` if the manager uses `AUDIT_API_KEY`. See `dashboard/.env.example`.

---

## Docker Compose (single deploy)

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) with **Compose** (`docker compose`).

From the **repository root** (`performance-audit-tool/`):

```bash
docker compose build
docker compose up
```

Leave that running; then open the UI at **http://localhost:3000**.

| Service | URL | Notes |
|--------|-----|--------|
| **Dashboard** | http://localhost:3000 | Static build behind nginx (port **3000** → container **80**). |
| **Manager API** | http://127.0.0.1:8001 | SQLite file in volume `manager_data` (`AUDIT_DB_PATH=/data/results.db`). |
| **Target API** (sample app) | http://127.0.0.1:8000 | What load tests hit. |

**Docker-only hosting:** you do not need Python or Node on the host — only Docker. Run `docker compose up --build` from the repo root; open **http://localhost:3000**.

**How the browser talks to the manager:** nginx serves the React app and **proxies** `/api` to `manager-api`, so the UI uses same-origin URLs like `/api/health` (no separate port for the API in the browser).

**How the manager reaches the target:** load tests run **inside** the manager container. If the target URL were `http://localhost:8000`, traffic would stay inside that container (wrong service) and you get **0 ms latency, 100% errors**, and a flat chart. The Compose file sets **`AUDIT_REPLACE_LOCALHOST_TARGET=http://target-api:8000`** on the manager so `localhost` / `127.0.0.1` bases are rewritten to the **`target-api`** service. The dashboard build also uses **`REACT_APP_TARGET_URL=http://target-api:8000`**.

**Flatline at 0 ms + high error %:** almost always “manager cannot reach the target.” After changing Compose or env, run **`docker compose up --build`** and confirm **http://127.0.0.1:8000/health** from the host (target is up).

**Checks**

- Dashboard (proxied API): http://localhost:3000/api/health (same browser origin as the UI)  
- Manager directly: http://127.0.0.1:8001/api/health  
- Target: http://127.0.0.1:8000/health  

If you see **NetworkError** or “Cannot reach manager API”, the manager container is not running or the dashboard image was built with the wrong API URL. From the repo root run **`docker compose up --build`** so nginx can proxy `/api` to `manager-api`.

**`GET /api/report/…` returns 404:** the HTML report is loaded from the **manager’s SQLite** by run ID. A 404 means that **`test_id` is not in the current database** — for example you opened an old bookmark or tab after **`docker compose down -v`** (volume wiped), or the ID was copied from another machine. Run a new audit and use **Report** from the **History** table for a row that exists now.

**Background / stop**

```bash
docker compose up -d    # detached
docker compose down     # stop and remove containers (volume keeps the DB)
```

To point the static build at a manager **without** nginx (not recommended for Compose), rebuild the dashboard with `REACT_APP_API_URL` set to the manager’s public URL.

---

## SQLite backups

- **Copy the file:** stop the manager (or rely on WAL) and copy `results.db` (or the path in `AUDIT_DB_PATH`).
- The manager enables **WAL mode** (`PRAGMA journal_mode=WAL`) for safer concurrent reads while writes complete.
- Optional: schedule `GET /api/export/history.json` to a file for a simple archive.

---

## Security notes

- **`AUDIT_API_KEY`** protects write-style operations when the manager is reachable beyond localhost. The dashboard can send `REACT_APP_AUDIT_API_KEY`, but **any value in the frontend bundle is visible** — prefer a reverse proxy or VPN for real protection.
- **`AUDIT_ALLOWED_TARGET_HOSTS`** reduces open-proxy risk when many users share one manager.
- **`AUDIT_RATE_LIMIT_PER_MINUTE`** limits abuse of `POST /api/tests/run`.

---

## CI and tests

- **Backend:** `cd manager-api && pip install -r requirements-dev.txt && pytest tests/ -v`
- **Dashboard:** `cd dashboard && npm ci && npm run build`
- **Smoke (manager must be running):** `MANAGER_URL=http://127.0.0.1:8001 bash scripts/smoke.sh`

GitHub Actions (`.github/workflows/ci.yml`) runs pytest and the dashboard build on push/PR.

---

## Where the ML runs

All **machine learning is server-side** in **`manager-api/intelligence.py`** (scikit-learn):

- **IsolationForest** on scaled multivariate features per endpoint (with a **modified Z / MAD** fallback when history is short).
- **LinearRegression** on run index vs P99 for a simple next-step forecast.
- **Feature “explainability”**: scaled distance from the training centroid per dimension.
- **`ai_summary`**: short natural-language headline plus a **confidence** hint tied to sample size (v2 bundle).

Load tests run **asynchronously**: **`POST /api/tests/run`** returns `{ "job_id" }`; poll **`GET /api/tests/jobs/{job_id}`** for `progress` / `total` and the final `result` (including intelligence). Heuristic SLO/diagnostics live in `slo.py` and `diagnostics.py` (rule-based, not neural nets). **`GET /api/tests/{id}/intelligence`** still returns the full bundle for a stored run.

---

## Operating the UI

1. Start all three processes (target, manager, dashboard).
2. The header shows **Manager online/offline** (polls **`GET /api/health`**).
3. Choose endpoint, load shape, requests, concurrency → **Run audit** (progress bar reflects completed requests).
4. **History** supports search, SLA filter, optional time range, and paging.
5. Select a row for **Insights**; **Pin baseline** shows which run you compare against; **Clear** removes the pin for that URL.
6. **Report** opens the HTML report (print to PDF from the browser if needed).
7. **CSV** / **JSON** in the header download full history.

---

## Project layout

```
performance-audit-tool/
├── target-api/          # Sample service under test
├── manager-api/         # FastAPI, SQLite, load engine, intelligence/
├── dashboard/           # React UI
├── scripts/             # smoke.sh helper
├── docker-compose.yml
└── README.md
```
