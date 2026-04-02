import os
import sys
import tempfile
from pathlib import Path

# Package root so `import database` works when pytest cwd is manager-api/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Must run before manager-api modules import database (DB_PATH reads env at import).
_fd, _TEST_DB = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["AUDIT_DB_PATH"] = _TEST_DB


def pytest_sessionfinish(session, exitstatus):
    try:
        os.unlink(_TEST_DB)
    except OSError:
        pass


import pytest


@pytest.fixture(autouse=True)
def clean_tables():
    import database

    database.init_db()
    conn = database._conn()
    conn.execute("DELETE FROM test_runs")
    conn.execute("DELETE FROM baselines")
    conn.execute("DELETE FROM audit_log")
    conn.commit()
    conn.close()
    yield
