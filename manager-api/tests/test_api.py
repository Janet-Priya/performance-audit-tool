import os

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client():
    os.environ.pop("AUDIT_API_KEY", None)
    import main

    return TestClient(main.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_history_shape(client):
    r = client.get("/api/tests/history")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert data["items"] == []


def test_history_filter_status(client):
    import database

    database.save_test_result(
        {
            "test_id": "t1",
            "endpoint_url": "http://localhost:8000/x",
            "method": "GET",
            "total_requests": 10,
            "concurrency": 1,
            "avg_latency": 10.0,
            "p50_latency": 10.0,
            "p99_latency": 20.0,
            "min_latency": 5.0,
            "max_latency": 25.0,
            "success_rate": 100.0,
            "error_rate": 0.0,
            "throughput_rps": 5.0,
            "status": "PASS",
            "timestamp": "2026-01-01T00:00:00",
            "load_profile": "flat",
            "ramp_peak_concurrency": None,
            "ramp_steps": 5,
            "wall_duration_sec": 1.0,
        }
    )
    r = client.get("/api/tests/history", params={"status": "PASS"})
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_engine_stats():
    import engine

    stats = engine.calculate_statistics(
        [
            {"success": True, "latency_ms": 10, "start_time": 0, "end_time": 1},
            {"success": True, "latency_ms": 20, "start_time": 0, "end_time": 1},
        ]
    )
    assert stats["total_requests"] == 2
    assert stats["avg_latency"] == 15.0


def test_report_404(client):
    r = client.get("/api/report/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_resolve_localhost_target(monkeypatch):
    import target_validation

    monkeypatch.delenv("AUDIT_REPLACE_LOCALHOST_TARGET", raising=False)
    assert target_validation.resolve_target_url("http://localhost:8000") == "http://localhost:8000"

    monkeypatch.setenv("AUDIT_REPLACE_LOCALHOST_TARGET", "http://target-api:8000")
    assert target_validation.resolve_target_url("http://localhost:8000") == "http://target-api:8000"
    assert target_validation.resolve_target_url("http://127.0.0.1:8000") == "http://target-api:8000"
    assert target_validation.resolve_target_url("http://target-api:8000") == "http://target-api:8000"
