"""Optional API key for mutating routes when AUDIT_API_KEY is set."""
from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def require_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> None:
    expected = (os.environ.get("AUDIT_API_KEY") or "").strip()
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
