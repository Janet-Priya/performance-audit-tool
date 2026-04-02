#!/usr/bin/env bash
set -euo pipefail
BASE="${MANAGER_URL:-http://127.0.0.1:8001}"
curl -sf "$BASE/api/health" | grep -q '"ok"'
echo "OK: $BASE/api/health"
