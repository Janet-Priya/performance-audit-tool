"""Merge helpers: baseline regression deltas."""
from __future__ import annotations

from typing import Any, Dict, Optional


def regression_vs_baseline(current: Dict[str, Any], baseline: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not baseline:
        return {"has_baseline": False}

    d_avg = float(current["avg_latency"]) - float(baseline["avg_latency"])
    d_p99 = float(current["p99_latency"]) - float(baseline["p99_latency"])
    d_err = float(current["error_rate"]) - float(baseline["error_rate"])
    d_rps = float(current["throughput_rps"]) - float(baseline["throughput_rps"])

    severity = "none"
    if d_p99 > 120 or d_avg > 100 or d_err > 5:
        severity = "severe"
    elif d_p99 > 40 or d_avg > 40 or d_err > 2:
        severity = "warn"

    return {
        "has_baseline": True,
        "baseline_test_id": baseline["test_id"],
        "baseline_timestamp": baseline.get("timestamp"),
        "delta_avg_ms": round(d_avg, 2),
        "delta_p99_ms": round(d_p99, 2),
        "delta_error_rate_pct": round(d_err, 2),
        "delta_throughput_rps": round(d_rps, 2),
        "regression_severity": severity,
    }
