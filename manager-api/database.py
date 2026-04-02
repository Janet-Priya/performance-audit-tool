import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

DB_PATH = "results.db"


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS test_runs (
            test_id TEXT PRIMARY KEY,
            endpoint_url TEXT,
            method TEXT,
            total_requests INTEGER,
            concurrency INTEGER,
            avg_latency REAL,
            p50_latency REAL,
            p99_latency REAL,
            min_latency REAL,
            max_latency REAL,
            success_rate REAL,
            error_rate REAL,
            throughput_rps REAL,
            status TEXT,
            timestamp TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS baselines (
            endpoint_url TEXT PRIMARY KEY,
            baseline_test_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT
        )
    """
    )
    conn.commit()
    conn.close()
    migrate_schema()


def migrate_schema():
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(test_runs)")
    existing = {row[1] for row in cursor.fetchall()}
    alters = [
        ("load_profile", "TEXT DEFAULT 'flat'"),
        ("ramp_peak_concurrency", "INTEGER"),
        ("ramp_steps", "INTEGER DEFAULT 5"),
        ("wall_duration_sec", "REAL"),
    ]
    for col, decl in alters:
        if col not in existing:
            cursor.execute(f"ALTER TABLE test_runs ADD COLUMN {col} {decl}")
    conn.commit()
    conn.close()


def append_audit(action: str, detail: str = ""):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audit_log (ts, action, detail) VALUES (?, ?, ?)",
        (datetime.utcnow().isoformat(), action, detail[:4000]),
    )
    conn.commit()
    conn.close()


def save_test_result(data: Dict[str, Any]):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO test_runs (
            test_id, endpoint_url, method, total_requests, concurrency,
            avg_latency, p50_latency, p99_latency, min_latency, max_latency,
            success_rate, error_rate, throughput_rps, status, timestamp,
            load_profile, ramp_peak_concurrency, ramp_steps, wall_duration_sec
        ) VALUES (
            :test_id, :endpoint_url, :method, :total_requests, :concurrency,
            :avg_latency, :p50_latency, :p99_latency, :min_latency, :max_latency,
            :success_rate, :error_rate, :throughput_rps, :status, :timestamp,
            :load_profile, :ramp_peak_concurrency, :ramp_steps, :wall_duration_sec
        )
    """,
        data,
    )
    conn.commit()
    conn.close()


def get_all_tests():
    conn = _conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM test_runs ORDER BY timestamp DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_test_by_id(test_id: str):
    conn = _conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM test_runs WHERE test_id = ?", (test_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_endpoint_history_chronological_upto(endpoint_url: str, test_id: str, limit: int = 40):
    """Oldest-first runs for an endpoint up to and including test_id (for historical insight view)."""
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp FROM test_runs WHERE test_id = ?", (test_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return []
    ts = row[0]
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM test_runs
        WHERE endpoint_url = ? AND timestamp <= ?
        ORDER BY timestamp ASC
        LIMIT ?
        """,
        (endpoint_url, ts, limit),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_recent_by_endpoint(endpoint_url: str, limit: int = 25):
    conn = _conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM test_runs
        WHERE endpoint_url = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (endpoint_url, limit),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return list(reversed(rows))


def set_baseline(endpoint_url: str, baseline_test_id: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM baselines WHERE endpoint_url = ?", (endpoint_url,))
    cursor.execute(
        "INSERT INTO baselines (endpoint_url, baseline_test_id, created_at) VALUES (?, ?, ?)",
        (endpoint_url, baseline_test_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_baseline_for_endpoint(endpoint_url: str) -> Optional[str]:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT baseline_test_id FROM baselines WHERE endpoint_url = ?",
        (endpoint_url,),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def clear_baseline(endpoint_url: str) -> bool:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM baselines WHERE endpoint_url = ?", (endpoint_url,))
    n = cursor.rowcount
    conn.commit()
    conn.close()
    return n > 0


def list_baselines():
    conn = _conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM baselines ORDER BY created_at DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def list_audit(limit: int = 200):
    conn = _conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
