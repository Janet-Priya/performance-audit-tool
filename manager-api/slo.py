"""
Lightweight SLO / error-budget style metrics for thesis narrative.
Not a full multi-window SLO engine — a tractable approximation on stored runs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Nominal targets (tune in report)
P99_TARGET_MS = 400.0
ERROR_BUDGET_PCT = 2.0  # max acceptable error rate % per "good" run
WINDOW = 12  # last N runs for budget estimate


def _run_meets_slo(p99_ms: float, err_pct: float) -> bool:
    return p99_ms <= P99_TARGET_MS and err_pct <= ERROR_BUDGET_PCT


def compute_slo_bundle(
    current: Dict[str, Any],
    recent_chronological: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    recent_chronological: oldest first, may include current as last.
    """
    p99 = float(current["p99_latency"])
    err = float(current["error_rate"])
    meets = _run_meets_slo(p99, err)

    window = recent_chronological[-WINDOW:] if len(recent_chronological) >= 1 else []
    if not window:
        return {
            "targets": {"p99_ms": P99_TARGET_MS, "max_error_pct": ERROR_BUDGET_PCT},
            "current_meets_slo": meets,
            "error_budget_remaining_pct": None,
            "burn_rate": None,
            "window_runs": 0,
        }

    bad = sum(1 for r in window if not _run_meets_slo(float(r["p99_latency"]), float(r["error_rate"])))
    budget_remaining = max(0.0, 100.0 * (1.0 - bad / max(1, len(window))))

    half = max(1, len(window) // 2)
    first = window[:half]
    second = window[half:]
    bad_first = sum(1 for r in first if not _run_meets_slo(float(r["p99_latency"]), float(r["error_rate"])))
    bad_second = sum(1 for r in second if not _run_meets_slo(float(r["p99_latency"]), float(r["error_rate"])))
    rate_first = bad_first / len(first)
    rate_second = bad_second / len(second)
    burn = rate_second - rate_first  # positive => degrading

    return {
        "targets": {"p99_ms": P99_TARGET_MS, "max_error_pct": ERROR_BUDGET_PCT},
        "current_meets_slo": meets,
        "error_budget_remaining_pct": round(budget_remaining, 2),
        "burn_rate": round(burn, 4),
        "window_runs": len(window),
        "bad_runs_in_window": bad,
    }
