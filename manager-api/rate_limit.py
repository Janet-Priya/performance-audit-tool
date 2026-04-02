"""Simple in-memory rate limit for POST /api/tests/run (per client IP)."""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import DefaultDict, List

from fastapi import HTTPException, Request

_window: DefaultDict[str, List[float]] = defaultdict(list)


def check_run_rate_limit(request: Request) -> None:
    limit = int((os.environ.get("AUDIT_RATE_LIMIT_PER_MINUTE") or "30").strip() or "30")
    if limit <= 0:
        return
    window_sec = 60.0
    client = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _window[client]
    bucket[:] = [t for t in bucket if now - t < window_sec]
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: max {limit} load-test runs per minute from this client",
        )
    bucket.append(now)
