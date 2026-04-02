from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
import csv
import html
import io
import json
import os
from typing import Optional

import database
import dependencies
import jobs
import rate_limit
import security
import target_validation
import config as app_config

app = FastAPI(title=app_config.api_title())

_default_cors = "http://localhost:3000,http://127.0.0.1:3000"
_cors = [o.strip() for o in os.environ.get("AUDIT_CORS_ORIGINS", _default_cors).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

database.init_db()


@app.get("/")
def root():
    """Browser or curl on the server root — API lives under /api/… and /docs."""
    return {
        "message": "Latency audit API",
        "interactive_docs": "/docs",
        "openapi_json": "/openapi.json",
        "examples": {
            "settings": "/api/settings",
            "history": "/api/tests/history",
            "run_test": "POST /api/tests/run",
        },
    }


@app.get("/api/settings")
def public_settings():
    """Branding copy for UI and docs — driven by environment variables."""
    return app_config.get_public_settings()


class TestConfig(BaseModel):
    target_url: str
    endpoint: str
    method: str = "GET"
    total_requests: int = 100
    concurrency: int = 10
    load_profile: str = "flat"
    ramp_peak_concurrency: Optional[int] = None
    ramp_steps: int = 5


class PinBaselineBody(BaseModel):
    test_id: str


def _rate_limit_dep(request: Request) -> None:
    rate_limit.check_run_rate_limit(request)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "latency-audit-manager"}


@app.post("/api/tests/run")
async def run_test(
    config: TestConfig,
    _auth: None = Depends(security.require_api_key),
    _rl: None = Depends(_rate_limit_dep),
):
    resolved = target_validation.resolve_target_url(config.target_url)
    target_validation.validate_target_url(resolved)
    is_ramp = (config.load_profile or "").lower() == "ramp"
    job_id = jobs.schedule_job(
        resolved,
        config.endpoint,
        config.method,
        config.total_requests,
        config.concurrency,
        load_profile=config.load_profile,
        ramp_peak_concurrency=config.ramp_peak_concurrency if is_ramp else None,
        ramp_steps=config.ramp_steps if is_ramp else 5,
    )
    return {"job_id": job_id}


@app.get("/api/tests/jobs/{job_id}")
def get_job_status(job_id: str):
    j = jobs.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    out = {
        "job_id": j.id,
        "status": j.status,
        "progress": j.progress,
        "total": j.total,
    }
    if j.error:
        out["error"] = j.error
    if j.status == "completed" and j.result:
        out["result"] = j.result
    return out


@app.get("/api/tests/history")
def get_history(
    q: str = Query("", description="Search endpoint URL, method, or test id"),
    status: Optional[str] = Query(None, description="PASS, WARN, or FAIL"),
    from_ts: Optional[str] = Query(None, description="ISO timestamp lower bound"),
    to_ts: Optional[str] = Query(None, description="ISO timestamp upper bound"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    items, total = database.get_tests_filtered(
        q=q,
        status=status,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/tests/{test_id}")
def get_test(test_id: str):
    result = database.get_test_by_id(test_id)
    if not result:
        raise HTTPException(status_code=404, detail="Test not found")
    return result


@app.get("/api/tests/{test_id}/intelligence")
def get_test_intelligence(test_id: str):
    result = database.get_test_by_id(test_id)
    if not result:
        raise HTTPException(status_code=404, detail="Test not found")
    hist = database.get_endpoint_history_chronological_upto(result["endpoint_url"], test_id, limit=40)
    if not hist:
        hist = [result]
    return jobs.build_intelligence_bundle(result, hist)


@app.post("/api/baselines")
def pin_baseline(body: PinBaselineBody, _auth: None = Depends(security.require_api_key)):
    t = database.get_test_by_id(body.test_id)
    if not t:
        raise HTTPException(status_code=404, detail="Test not found")
    database.set_baseline(t["endpoint_url"], body.test_id)
    database.append_audit("baseline_pin", f"{t['endpoint_url']} -> {body.test_id}")
    return {"ok": True, "endpoint_url": t["endpoint_url"], "baseline_test_id": body.test_id}


@app.get("/api/baselines")
def get_baselines():
    rows = database.list_baselines()
    out = []
    for b in rows:
        tr = database.get_test_by_id(b["baseline_test_id"])
        out.append({**b, "baseline_snapshot": tr})
    return out


@app.delete("/api/baselines")
def delete_baseline(
    endpoint_url: str = Query(..., description="Full endpoint URL as stored, e.g. http://localhost:8000/login"),
    _auth: None = Depends(security.require_api_key),
):
    ok = database.clear_baseline(endpoint_url)
    if not ok:
        raise HTTPException(status_code=404, detail="No baseline for that URL")
    database.append_audit("baseline_clear", endpoint_url)
    return {"ok": True}


@app.get("/api/dependencies")
def dep_view(path: str = Query("/login", description="Path like /login")):
    return dependencies.blast_radius_for_path(path)


@app.get("/api/dependencies/graph")
def dep_graph():
    return dependencies.full_graph()


@app.get("/api/audit")
def audit_log(limit: int = Query(100, ge=1, le=500)):
    return database.list_audit(limit)


@app.get("/api/export/history.json")
def export_json():
    data = database.get_all_tests()
    database.append_audit("export_json", f"rows={len(data)}")
    return Response(content=json.dumps(data, indent=2), media_type="application/json")


@app.get("/api/export/history.csv")
def export_csv():
    rows = database.get_all_tests()
    if not rows:
        return Response(content="", media_type="text/csv")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    database.append_audit("export_csv", f"rows={len(rows)}")
    return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8")


@app.get("/api/report/{test_id}", response_class=HTMLResponse)
def get_report(test_id: str):
    result = database.get_test_by_id(test_id)
    if not result:
        raise HTTPException(status_code=404, detail="Test not found")

    status = result["status"]
    accent = {"PASS": "#34d399", "WARN": "#fbbf24", "FAIL": "#f87171"}.get(status, "#94a3b8")
    bg_badge = {"PASS": "rgba(16,185,129,0.2)", "WARN": "rgba(245,158,11,0.2)", "FAIL": "rgba(239,68,68,0.2)"}.get(
        status, "rgba(100,116,139,0.2)"
    )

    def g(key, default=""):
        v = result.get(key)
        return default if v is None else v

    def fmt_sec(v):
        if v is None:
            return "—"
        try:
            return f"{float(v):.3f}"
        except (TypeError, ValueError):
            return "—"

    ep = html.escape(str(result["endpoint_url"]))
    tid = html.escape(str(result["test_id"]))
    load_profile = html.escape(str(g("load_profile", "flat") or "flat"))
    wall_s = fmt_sec(g("wall_duration_sec"))
    ramp_peak = g("ramp_peak_concurrency")
    ramp_peak_s = html.escape(str(ramp_peak)) if ramp_peak is not None else "—"
    ramp_steps = g("ramp_steps")
    ramp_steps_s = html.escape(str(ramp_steps)) if ramp_steps is not None else "—"

    settings = app_config.get_public_settings()
    h1 = html.escape(app_config.report_heading())
    sub_raw = (settings.get("report_subtitle") or "").strip()
    sub_html = f'<p class="sub">{html.escape(sub_raw)}</p>' if sub_raw else ""
    footer_line = html.escape(settings.get("report_footer") or "")

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Audit report · {status}</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100vh;
    font-family: "Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif;
    background: radial-gradient(1200px 600px at 10% -10%, rgba(56,189,248,0.1), transparent 50%),
      radial-gradient(800px 400px at 100% 0%, rgba(167,139,250,0.08), transparent 45%),
      #06080c;
    color: #f1f5f9;
    padding: 48px 24px 64px;
  }}
  .wrap {{ max-width: 880px; margin: 0 auto; }}
  .top {{
    display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 20px;
    margin-bottom: 28px;
  }}
  h1 {{
    margin: 0 0 6px;
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: -0.03em;
  }}
  .sub {{ color: #94a3b8; font-size: 0.9rem; max-width: 52ch; line-height: 1.5; }}
  .badge {{
    display: inline-flex;
    align-items: center;
    padding: 10px 18px;
    border-radius: 999px;
    font-weight: 700;
    font-size: 0.8rem;
    letter-spacing: 0.06em;
    color: {accent};
    background: {bg_badge};
    border: 1px solid rgba(148,163,184,0.25);
  }}
  .meta {{ font-size: 0.75rem; color: #64748b; margin-top: 12px; }}
  .mono {{ font-family: ui-monospace, monospace; font-size: 0.8rem; word-break: break-all; color: #cbd5e1; }}
  .card {{
    background: rgba(18, 22, 32, 0.75);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(148,163,184,0.12);
    border-radius: 16px;
    padding: 22px 24px;
    margin-bottom: 18px;
    box-shadow: 0 8px 40px rgba(0,0,0,0.35);
  }}
  .card h2 {{
    margin: 0 0 16px;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #64748b;
  }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }}
  .metric {{
    background: rgba(8, 11, 18, 0.55);
    border: 1px solid rgba(148,163,184,0.08);
    border-radius: 12px;
    padding: 14px 16px;
  }}
  .metric-label {{ font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; margin-bottom: 6px; }}
  .metric-value {{ font-size: 1.35rem; font-weight: 700; color: #f1f5f9; letter-spacing: -0.02em; }}
  .metric-value.sm {{ font-size: 0.95rem; font-weight: 500; line-height: 1.4; }}
  .footer {{ text-align: center; color: #475569; font-size: 0.8rem; margin-top: 36px; }}
  @media print {{
    body {{ background: #fff; color: #0f172a; padding: 24px; }}
    .card {{ box-shadow: none; border: 1px solid #e2e8f0; }}
    .metric {{ background: #f8fafc; }}
    .metric-value {{ color: #0f172a; }}
    .sub {{ color: #475569; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1>{h1}</h1>
      {sub_html}
      <p class="meta">Run ID <span class="mono">{tid}</span></p>
    </div>
    <div><span class="badge">SLA {status}</span></div>
  </div>

  <div class="card">
    <h2>Configuration</h2>
    <div class="grid">
      <div class="metric"><div class="metric-label">Endpoint</div><div class="metric-value sm">{ep}</div></div>
      <div class="metric"><div class="metric-label">Method</div><div class="metric-value">{html.escape(str(result["method"]))}</div></div>
      <div class="metric"><div class="metric-label">Requests</div><div class="metric-value">{result["total_requests"]}</div></div>
      <div class="metric"><div class="metric-label">Concurrency</div><div class="metric-value">{result["concurrency"]}</div></div>
      <div class="metric"><div class="metric-label">Load profile</div><div class="metric-value sm">{load_profile}</div></div>
      <div class="metric"><div class="metric-label">Wall time</div><div class="metric-value sm">{html.escape(wall_s)}{'' if wall_s == '—' else ' s'}</div></div>
      <div class="metric"><div class="metric-label">Ramp peak</div><div class="metric-value sm">{ramp_peak_s}</div></div>
      <div class="metric"><div class="metric-label">Ramp steps</div><div class="metric-value sm">{ramp_steps_s}</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Latency</h2>
    <div class="grid">
      <div class="metric"><div class="metric-label">Average</div><div class="metric-value">{result['avg_latency']} ms</div></div>
      <div class="metric"><div class="metric-label">P99</div><div class="metric-value" style="color:{accent}">{result['p99_latency']} ms</div></div>
      <div class="metric"><div class="metric-label">P50</div><div class="metric-value">{result['p50_latency']} ms</div></div>
      <div class="metric"><div class="metric-label">Min / Max</div><div class="metric-value sm">{result['min_latency']} / {result['max_latency']} ms</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Reliability</h2>
    <div class="grid">
      <div class="metric"><div class="metric-label">Success rate</div><div class="metric-value" style="color:#34d399">{result['success_rate']}%</div></div>
      <div class="metric"><div class="metric-label">Error rate</div><div class="metric-value" style="color:#f87171">{result['error_rate']}%</div></div>
      <div class="metric"><div class="metric-label">Throughput</div><div class="metric-value">{result['throughput_rps']} RPS</div></div>
      <div class="metric"><div class="metric-label">Recorded at</div><div class="metric-value sm">{html.escape(str(result['timestamp'])[:19])} UTC</div></div>
    </div>
  </div>

  <p class="footer">{footer_line}</p>
</div>
</body>
</html>"""
    return HTMLResponse(content=html_out)
