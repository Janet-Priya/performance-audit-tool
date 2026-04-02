"""
Machine learning layer (scikit-learn, server-side):

- IsolationForest (+ StandardScaler) on per-endpoint feature history for anomaly scoring.
- LinearRegression for P99 trend / next-step forecast.
- Modified Z-score (median/MAD) when history is too short for the forest.
- Centroid-distance "explainability" over scaled features.

Consumed from main.py after each test run and via GET /api/tests/{id}/intelligence.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

# Tunables (document for thesis / review)
MIN_SAMPLES_IF = 6
MIN_SAMPLES_FORECAST = 4
CONTAMINATION = 0.12
WARN_AVG_MS = 200.0
FAIL_AVG_MS = 500.0

FEATURE_LABELS = ["p99_ms", "avg_ms", "p99_over_avg", "error_rate_pct", "throughput_rps", "delta_p99_ms"]


def _features_from_rows(rows: List[Dict[str, Any]]) -> np.ndarray:
    """Build feature matrix: p99, avg, p99/avg, error_rate, throughput, delta_p99."""
    feats: List[List[float]] = []
    for i, r in enumerate(rows):
        p99 = float(r["p99_latency"])
        avg = float(max(r["avg_latency"], 1e-6))
        prev_p99 = float(rows[i - 1]["p99_latency"]) if i > 0 else p99
        feats.append(
            [
                p99,
                float(r["avg_latency"]),
                p99 / avg,
                float(r["error_rate"]),
                float(r["throughput_rps"]),
                p99 - prev_p99,
            ]
        )
    return np.asarray(feats, dtype=np.float64)


def _modified_z_p99(rows: List[Dict[str, Any]], current_p99: float) -> Tuple[float, bool]:
    """Robust outlier flag when too few points for IF (median/MAD)."""
    p99s = [float(r["p99_latency"]) for r in rows]
    med = float(np.median(p99s))
    mad = float(np.median(np.abs(np.asarray(p99s) - med))) or 1e-6
    mod_z = 0.6745 * abs(current_p99 - med) / mad
    is_out = mod_z > 3.5
    return mod_z, is_out


def _isolation_score(
    rows: List[Dict[str, Any]],
) -> Tuple[Optional[float], bool, str]:
    """
    Train on all but last row; score the latest run.
    Returns (anomaly_score roughly in [-1,1] from decision function, is_anomaly, method).
    """
    if len(rows) < MIN_SAMPLES_IF:
        p99 = float(rows[-1]["p99_latency"])
        mz, is_out = _modified_z_p99(rows, p99)
        # Normalize rough score for UI
        score = min(1.0, mz / 5.0)
        return score, is_out, "modified_z_mad"

    X = _features_from_rows(rows)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    train_x = Xs[:-1]
    current_x = Xs[-1].reshape(1, -1)

    iso = IsolationForest(
        n_estimators=120,
        contamination=CONTAMINATION,
        random_state=42,
        max_samples=max(2, len(train_x)),
    )
    iso.fit(train_x)
    pred = int(iso.predict(current_x)[0])
    dec = float(iso.decision_function(current_x)[0])
    # sklearn: -1 = anomaly, 1 = normal
    is_anomaly = pred == -1
    return dec, is_anomaly, "isolation_forest"


def _forecast_p99(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if n < MIN_SAMPLES_FORECAST:
        return {
            "next_p99_ms": None,
            "slope_ms_per_run": None,
            "stderr_hint": None,
            "usable": False,
        }
    y = np.array([float(r["p99_latency"]) for r in rows], dtype=np.float64)
    t = np.arange(n, dtype=np.float64).reshape(-1, 1)
    reg = LinearRegression()
    reg.fit(t, y)
    next_t = np.array([[n]], dtype=np.float64)
    next_p99 = float(reg.predict(next_t)[0])
    slope = float(reg.coef_[0])
    # Residual std for a simple uncertainty hint
    pred_in = reg.predict(t)
    resid = y - pred_in
    stderr = float(np.std(resid)) if n > 2 else 0.0
    return {
        "next_p99_ms": round(max(0.0, next_p99), 2),
        "slope_ms_per_run": round(slope, 4),
        "stderr_hint": round(stderr, 2),
        "usable": True,
    }


def _composite_risk(
    is_anomaly: bool,
    anomaly_method: str,
    avg_ms: float,
    forecast: Dict[str, Any],
    error_rate: float,
) -> int:
    """0–100 higher = more risk (for dashboard gauge)."""
    score = 0.0
    if is_anomaly:
        score += 38 if anomaly_method == "isolation_forest" else 28
    if avg_ms >= FAIL_AVG_MS:
        score += 35
    elif avg_ms >= WARN_AVG_MS:
        score += 18
    if error_rate > 2:
        score += min(25.0, error_rate * 2)
    fc = forecast.get("next_p99_ms")
    if fc is not None and forecast.get("usable"):
        if fc >= FAIL_AVG_MS:
            score += 22
        elif fc >= WARN_AVG_MS:
            score += 10
    return int(min(100, round(score)))


def _recommendations(
    rows: List[Dict[str, Any]],
    is_anomaly: bool,
    forecast: Dict[str, Any],
    avg_ms: float,
    p99_ms: float,
    error_rate: float,
    slope: Optional[float],
) -> List[str]:
    out: List[str] = []
    spread = p99_ms - avg_ms
    if spread > 200:
        out.append(
            "Tail latency (P99) is much higher than average — investigate long-tail causes "
            "(GC pauses, cold caches, blocking I/O, or occasional slow dependencies)."
        )
    elif spread < 20 and avg_ms > WARN_AVG_MS:
        out.append(
            "Average and tail are both elevated — likely systematic slowdown, not sporadic spikes."
        )

    if is_anomaly:
        out.append(
            "Multivariate anomaly: this run’s latency profile deviates from your recent baseline "
            "for this endpoint — treat as an early warning even if SLA still passes."
        )

    if slope is not None and slope > 1.0 and forecast.get("usable"):
        out.append(
            f"Regression trend is rising (~{slope:.2f} ms per run on P99). "
            "If load is unchanged, schedule profiling or capacity review before the next release."
        )
    elif slope is not None and slope < -0.5:
        out.append("P99 trend is improving — keep monitoring to confirm the gain holds.")

    fc = forecast.get("next_p99_ms")
    if fc is not None and fc > WARN_AVG_MS and avg_ms < FAIL_AVG_MS:
        out.append(
            f"Forecast suggests P99 may reach ~{fc:.0f} ms on the next run if the trend continues."
        )

    if error_rate > 5:
        out.append(
            "Non-trivial error rate — check timeouts, 5xxs, and client-side retries; errors distort latency."
        )

    if not out:
        out.append(
            "No strong risk signals — continue periodic audits after deploys or config changes."
        )
    return out[:6]


def explain_deviation_from_training(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Cheap explainability: scaled distance of the latest point from the training centroid
    (which dimensions look most 'off' vs recent history).
    """
    if len(rows) < MIN_SAMPLES_IF:
        return {"method": "modified_z", "top_features": [], "note": "Need more history for multivariate view."}
    X = _features_from_rows(rows)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    train = Xs[:-1]
    cur = Xs[-1]
    center = np.mean(train, axis=0)
    delta = np.abs(cur - center)
    order = np.argsort(-delta)
    top = []
    for idx in order[:4]:
        top.append(
            {
                "feature": FEATURE_LABELS[int(idx)],
                "scaled_abs_deviation": round(float(delta[idx]), 4),
            }
        )
    return {"method": "train_centroid_distance", "top_features": top}


def analyze_endpoint_history(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    rows: chronological order for one endpoint, including the latest run as last element.
    """
    if not rows:
        return {
            "engine": "composite_latency_intelligence_v1",
            "anomaly": {"is_anomaly": False, "score": None, "method": "none"},
            "forecast": {"next_p99_ms": None, "slope_ms_per_run": None, "stderr_hint": None, "usable": False},
            "composite_risk": 0,
            "recommendations": ["No history for this endpoint yet."],
            "explainability": {"method": "none", "top_features": []},
        }

    last = rows[-1]
    avg_ms = float(last["avg_latency"])
    p99_ms = float(last["p99_latency"])
    err = float(last["error_rate"])

    anom_score, is_anom, method = _isolation_score(rows)
    forecast = _forecast_p99(rows)
    slope = forecast.get("slope_ms_per_run")

    risk = _composite_risk(is_anom, method, avg_ms, forecast, err)

    recs = _recommendations(rows, is_anom, forecast, avg_ms, p99_ms, err, slope)
    explain = explain_deviation_from_training(rows)

    return {
        "engine": "composite_latency_intelligence_v1",
        "anomaly": {
            "is_anomaly": bool(is_anom),
            "score": None if anom_score is None else round(float(anom_score), 4),
            "method": method,
            "history_runs": len(rows),
        },
        "forecast": forecast,
        "trend": {
            "direction": "flat"
            if slope is None
            else ("up" if slope > 0.5 else "down" if slope < -0.5 else "flat"),
            "slope_ms_per_run": slope,
        },
        "composite_risk": risk,
        "recommendations": recs,
        "explainability": explain,
    }
