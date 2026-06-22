#!/usr/bin/env bash
# HA Add-on entrypoint. Maps /data/options.json fields to env vars and execs uvicorn on 8001.
set -euo pipefail

OPTIONS_FILE="/data/options.json"

if [ -f "$OPTIONS_FILE" ]; then
  echo "[desk] reading options from $OPTIONS_FILE"
  python3 - "$OPTIONS_FILE" <<'PY' >/tmp/desk.env
import json
import shlex
import sys

with open(sys.argv[1]) as f:
    opts = json.load(f)

mapping = {
    "loft_internal_url":   "LOFT_INTERNAL_URL",
    "ical_url":            "ICAL_URL",
    "oura_client_id":      "OURA_CLIENT_ID",
    "oura_client_secret":  "OURA_CLIENT_SECRET",
    "dashboard_base_url":  "DASHBOARD_BASE_URL",
    "log_level":           "LOG_LEVEL",
}

for src, dst in mapping.items():
    if src not in opts:
        continue
    val = opts[src]
    if val is None or val == "":
        continue
    print(f"export {dst}={shlex.quote(str(val))}")
PY
  # shellcheck disable=SC1091
  . /tmp/desk.env
fi

# Tokens file lives in the HA persistent per-Add-on volume.
export OURA_TOKENS_PATH="/data/oura_tokens.json"

exec uvicorn app.main:app \
  --app-dir /app/backend \
  --host 0.0.0.0 \
  --port 8001 \
  --proxy-headers \
  --forwarded-allow-ips='*'
