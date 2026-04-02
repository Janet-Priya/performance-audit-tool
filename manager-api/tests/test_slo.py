"""SLO bundle must not divide by zero with a single-run window."""
import slo


def test_slo_burn_rate_single_run_window():
    current = {"p99_latency": 50.0, "error_rate": 0.0}
    # One run only — previously second half was empty → ZeroDivisionError
    hist = [current]
    out = slo.compute_slo_bundle(current, hist)
    assert out["window_runs"] >= 1
    assert out.get("burn_rate") is None or isinstance(out.get("burn_rate"), (int, float))


def test_slo_burn_rate_two_runs():
    rows = [
        {"p99_latency": 100.0, "error_rate": 0.0},
        {"p99_latency": 120.0, "error_rate": 0.0},
    ]
    out = slo.compute_slo_bundle(rows[-1], rows)
    assert out["burn_rate"] is not None
