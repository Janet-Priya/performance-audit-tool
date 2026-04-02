"""
Static service dependency map for blast-radius hints (demo / thesis layer).
Replace with discovery data in production.
"""
from __future__ import annotations

from typing import Any, Dict, List

# path -> nodes that are known callers (upstream) and callees (downstream)
GRAPH: Dict[str, Dict[str, List[str]]] = {
    "/health": {"callers": [], "callees": []},
    "/login": {"callers": ["/get-data"], "callees": []},
    "/get-data": {"callers": ["/users"], "callees": ["/login"]},
    "/users": {"callers": ["/search"], "callees": ["/get-data"]},
    "/upload": {"callers": [], "callees": ["/notifications"]},
    "/search": {"callers": [], "callees": ["/users"]},
    "/notifications": {"callers": ["/upload"], "callees": []},
}


def path_from_url(endpoint_url: str) -> str:
    if "://" in endpoint_url:
        return "/" + endpoint_url.split("/", 3)[-1].lstrip("/") or "/"
    return endpoint_url if endpoint_url.startswith("/") else "/" + endpoint_url


def blast_radius_for_path(path: str) -> Dict[str, Any]:
    p = path if path.startswith("/") else "/" + path
    if p not in GRAPH:
        return {"path": p, "upstream": [], "downstream": [], "note": "No graph entry for this path."}
    node = GRAPH[p]
    return {
        "path": p,
        "upstream": list(node.get("callers", [])),
        "downstream": list(node.get("callees", [])),
        "note": "Synthetic map for demo; use mesh/tracing in production.",
    }


def full_graph() -> Dict[str, Any]:
    return {"nodes": list(GRAPH.keys()), "edges": GRAPH}
