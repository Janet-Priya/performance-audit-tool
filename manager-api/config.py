"""
Public branding — override with environment variables.
Legacy institution/person strings in env are ignored (treated as empty) so old shell exports cannot leak into the UI or reports.
"""
from __future__ import annotations

import os

# Substrings that invalidate branding env values (case-insensitive)
_LEGACY_MARKERS = (
    "janet",
    "priya",
    "saptang",
    "anna university",
    "710022",
    "aurcc",
    "karthika",
)


def _sanitize(value: str) -> str:
    if not value or not isinstance(value, str):
        return ""
    lower = value.lower()
    if any(m in lower for m in _LEGACY_MARKERS):
        return ""
    return value.strip()


def _env_clean(key: str, default: str) -> str:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    cleaned = _sanitize(raw)
    return cleaned if cleaned else default


def _env_clean_optional(key: str) -> str:
    raw = os.environ.get(key, "")
    if not raw:
        return ""
    return _sanitize(raw)


def get_public_settings() -> dict:
    return {
        "app_title": _env_clean("AUDIT_APP_TITLE", "Performance audit"),
        "app_subtitle": _env_clean(
            "AUDIT_APP_SUBTITLE",
            "Load testing and latency insights",
        ),
        "report_subtitle": _env_clean_optional("AUDIT_REPORT_SUBTITLE"),
        "report_footer": _env_clean(
            "AUDIT_REPORT_FOOTER",
            "Print this page (Ctrl/Cmd+P) to save as PDF",
        ),
    }


def api_title() -> str:
    return _env_clean("AUDIT_API_TITLE", "Latency audit API")


def report_heading() -> str:
    """Main H1 on the HTML report page."""
    raw_title = os.environ.get("AUDIT_REPORT_TITLE")
    if raw_title:
        cleaned = _sanitize(raw_title)
        if cleaned:
            return cleaned
    base = _env_clean("AUDIT_APP_TITLE", "Performance audit")
    return f"{base} report"
