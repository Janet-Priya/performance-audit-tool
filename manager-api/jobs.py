"""Background load-test jobs with progress (in-memory)."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import database
import engine
import intelligence
import slo
import diagnostics
import dependencies
import analysis


@dataclass
class Job:
    id: str
    status: str  # queued | running | completed | failed
    progress: int = 0
    total: int = 0
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)


JOBS: Dict[str, Job] = {}
_MAX_JOBS = 80


def _prune_jobs() -> None:
    if len(JOBS) <= _MAX_JOBS:
        return
    # drop oldest by created_at
    for jid, _ in sorted(JOBS.items(), key=lambda kv: kv[1].created_at)[: len(JOBS) - _MAX_JOBS + 10]:
        del JOBS[jid]


def create_job() -> str:
    _prune_jobs()
    jid = str(uuid.uuid4())
    JOBS[jid] = Job(id=jid, status="queued", total=0)
    return jid


def get_job(job_id: str) -> Optional[Job]:
    return JOBS.get(job_id)


def build_intelligence_bundle(test_row: dict, hist: list) -> dict:
    intel = intelligence.analyze_endpoint_history(hist)
    baseline_id = database.get_baseline_for_endpoint(test_row["endpoint_url"])
    baseline_row = database.get_test_by_id(baseline_id) if baseline_id else None
    intel["slo"] = slo.compute_slo_bundle(test_row, hist)
    intel["regression"] = analysis.regression_vs_baseline(test_row, baseline_row)
    intel["diagnostics"] = diagnostics.multi_signal_analysis(test_row, baseline_row)
    intel["dependencies"] = dependencies.blast_radius_for_path(
        dependencies.path_from_url(test_row["endpoint_url"])
    )
    return intel


async def run_job(
    job_id: str,
    target_url: str,
    endpoint: str,
    method: str,
    total_requests: int,
    concurrency: int,
    load_profile: str = "flat",
    ramp_peak_concurrency: Optional[int] = None,
    ramp_steps: int = 5,
) -> None:
    job = JOBS.get(job_id)
    if not job:
        return
    job.status = "running"
    job.total = max(1, int(total_requests))

    def on_progress(done: int, total: int) -> None:
        j = JOBS.get(job_id)
        if j:
            j.progress = done
            j.total = max(1, total)

    try:
        t0 = time.perf_counter()
        results = await engine.run_load_test(
            target_url,
            endpoint,
            method,
            total_requests,
            concurrency,
            load_profile=load_profile,
            ramp_peak_concurrency=ramp_peak_concurrency,
            ramp_steps=ramp_steps,
            progress_callback=on_progress,
        )
        wall = time.perf_counter() - t0
        stats = engine.calculate_statistics(results)

        avg = stats["avg_latency"]
        if avg < 200:
            status = "PASS"
        elif avg < 500:
            status = "WARN"
        else:
            status = "FAIL"

        test_id = str(uuid.uuid4())
        endpoint_url = target_url.rstrip("/") + endpoint
        is_ramp = (load_profile or "").lower() == "ramp"
        record = {
            "test_id": test_id,
            "endpoint_url": endpoint_url,
            "method": method.upper(),
            "total_requests": total_requests,
            "concurrency": concurrency,
            "avg_latency": stats["avg_latency"],
            "p50_latency": stats["p50_latency"],
            "p99_latency": stats["p99_latency"],
            "min_latency": stats["min_latency"],
            "max_latency": stats["max_latency"],
            "success_rate": stats["success_rate"],
            "error_rate": stats["error_rate"],
            "throughput_rps": stats["throughput_rps"],
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "load_profile": (load_profile or "flat").lower(),
            "ramp_peak_concurrency": ramp_peak_concurrency if is_ramp else None,
            "ramp_steps": ramp_steps if is_ramp else None,
            "wall_duration_sec": round(wall, 3),
        }
        database.save_test_result(record)
        database.append_audit("test_run", f"{endpoint_url} profile={record['load_profile']}")

        hist = database.get_recent_by_endpoint(endpoint_url, limit=25)
        intel = build_intelligence_bundle(record, hist)

        j = JOBS.get(job_id)
        if j:
            j.status = "completed"
            j.progress = j.total
            j.result = {
                "test_id": test_id,
                "status": status,
                **stats,
                "wall_duration_sec": record["wall_duration_sec"],
                "intelligence": intel,
            }
    except Exception as e:
        j = JOBS.get(job_id)
        if j:
            j.status = "failed"
            j.error = str(e)


def schedule_job(
    target_url: str,
    endpoint: str,
    method: str,
    total_requests: int,
    concurrency: int,
    load_profile: str = "flat",
    ramp_peak_concurrency: Optional[int] = None,
    ramp_steps: int = 5,
) -> str:
    jid = create_job()
    asyncio.create_task(
        run_job(
            jid,
            target_url,
            endpoint,
            method,
            total_requests,
            concurrency,
            load_profile=load_profile,
            ramp_peak_concurrency=ramp_peak_concurrency,
            ramp_steps=ramp_steps,
        )
    )
    return jid
