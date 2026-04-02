"""Restrict target_url host when AUDIT_ALLOWED_TARGET_HOSTS is set (comma-separated)."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import HTTPException


def resolve_target_url(target_url: str) -> str:
    """
    When the UI sends http://localhost:8000 or http://127.0.0.1:8000 but the manager runs in Docker,
    that host is the manager container itself — load tests get 0 ms + 100% errors.

    Set AUDIT_REPLACE_LOCALHOST_TARGET (e.g. http://target-api:8000) so the manager hits the real target service.
    """
    raw = (target_url or "").strip().rstrip("/")
    replacement = (os.environ.get("AUDIT_REPLACE_LOCALHOST_TARGET") or "").strip().rstrip("/")
    if not replacement or not raw:
        return raw
    try:
        p = urlparse(raw)
    except Exception:
        return raw
    host = (p.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return replacement
    return raw


def allowed_target_hosts() -> list[str] | None:
    raw = (os.environ.get("AUDIT_ALLOWED_TARGET_HOSTS") or "").strip()
    if not raw:
        return None
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def validate_target_url(target_url: str) -> None:
    hosts = allowed_target_hosts()
    if not hosts:
        return
    try:
        p = urlparse(target_url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid target_url")
    scheme = (p.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="target_url must use http or https")
    host = (p.hostname or "").lower()
    if not host:
        raise HTTPException(status_code=400, detail="target_url must include a host")
    if host not in hosts:
        raise HTTPException(
            status_code=400,
            detail=f"Target host '{host}' is not allowed. Set AUDIT_ALLOWED_TARGET_HOSTS or use an allowed host.",
        )
