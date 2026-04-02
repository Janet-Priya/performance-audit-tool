"""
Heuristic multi-signal correlation — not APM, but defensible pattern labels.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def multi_signal_analysis(
    current: Dict[str, Any],
    baseline: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    avg = float(current["avg_latency"])
    p99 = float(current["p99_latency"])
    err = float(current["error_rate"])
    rps = float(current["throughput_rps"])
    spread = p99 - avg

    hints: List[str] = []
    pattern = "steady"

    if baseline:
        b_p99 = float(baseline["p99_latency"])
        b_err = float(baseline["error_rate"])
        b_avg = float(baseline["avg_latency"])
        d_p99 = p99 - b_p99
        d_err = err - b_err
        d_avg = avg - b_avg

        if d_err > 3 and d_p99 < 50:
            pattern = "errors_without_tail_shift"
            hints.append(
                "Errors increased sharply while tail latency barely moved — check timeouts, "
                "connection resets, or upstream short-failing before work completes."
            )
        elif d_p99 > 80 and d_err < 2:
            pattern = "latency_without_errors"
            hints.append(
                "Latency worsened without a matching error spike — typical of saturation, "
                "queueing, GC, or slow dependencies still returning 2xx."
            )
        elif d_p99 > 80 and d_err > 3:
            pattern = "combined_regression"
            hints.append(
                "Both latency and errors moved together — likely overload, cascading failures, "
                "or a bad deploy affecting success path and tail."
            )
        elif abs(d_avg) < 15 and abs(d_p99) > 60:
            pattern = "tail_only_shift"
            hints.append(
                "Median-ish average stable but tail shifted — investigate outliers, retries, "
                "or rare slow paths rather than uniform slowdown."
            )
        elif d_avg < -20 and d_p99 < -20:
            pattern = "improvement"
            hints.append("Compared to pinned baseline, this run looks improved on average and tail.")
    else:
        hints.append("Pin a baseline run to unlock comparative diagnostics.")

    if spread > 250:
        hints.append(f"Large P99−avg gap ({spread:.0f} ms) — long-tail behaviour dominates the story.")
    elif spread < 30 and p99 > 300:
        hints.append("Tail and average are both high — broad slowdown rather than rare spikes.")

    if err > 8:
        hints.append("High error share — latency percentiles may under-represent user-visible failure.")

    if rps < 5 and avg > 200:
        hints.append("Throughput is low relative to typical web paths — possible client or network bottleneck.")

    if not hints:
        hints.append("No strong multi-signal pattern — keep collecting runs after changes.")

    return {"pattern": pattern, "signals": {"spread_ms": round(spread, 2)}, "hints": hints[:5]}
