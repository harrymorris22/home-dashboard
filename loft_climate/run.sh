#!/usr/bin/env bash
# HA Add-on entrypoint. Reads /data/options.json (populated from the Add-on UI),
# exports each option as the env var our backend already understands, then execs
# uvicorn.
set -euo pipefail

OPTIONS_FILE="/data/options.json"

if [ -f "$OPTIONS_FILE" ]; then
  echo "[loft_climate] reading options from $OPTIONS_FILE"
  python3 - "$OPTIONS_FILE" <<'PY' >/tmp/loft_climate.env
import json
import os
import shlex
import sys

with open(sys.argv[1]) as f:
    opts = json.load(f)

# Map Add-on option names → backend env vars.
mapping = {
    "weather_provider":          "WEATHER_PROVIDER",
    "weather_user_agent":        "WEATHER_USER_AGENT",
    "owm_api_key":               "OWM_API_KEY",
    "ha_token":                  "HA_TOKEN",
    "ha_entity_map":             "HA_ENTITY_MAP",
    "ha_outdoor_entities":       "HA_OUTDOOR_ENTITIES",
    "ha_sunshine_entity":        "HA_SUNSHINE_ENTITY",
    "ha_blind_entities":         "HA_BLIND_ENTITIES",
    "vapid_subject":             "VAPID_SUBJECT",
    "notify_email_smtp_password":"NOTIFY_EMAIL_SMTP_PASSWORD",
    "notify_email_to":           "NOTIFY_EMAIL_TO",
    "data_retention_days":       "DATA_RETENTION_DAYS",
}

for src, dst in mapping.items():
    if src not in opts:
        continue
    val = opts[src]
    if val is None or val == "":
        continue
    if isinstance(val, (dict, list)):
        rendered = json.dumps(val)
    else:
        rendered = str(val)
    print(f"export {dst}={shlex.quote(rendered)}")

# Inside HA Add-on: HA Core is reachable on the Pi's host network.
# Default to the supervisor's local proxy if no explicit URL is configured.
if not opts.get("ha_base_url"):
    print("export HA_BASE_URL=http://homeassistant.local:8123")
PY
  # shellcheck disable=SC1091
  . /tmp/loft_climate.env
fi

# Latitude/longitude default to N1 7RR via the checked-in config.json defaults.
# OWM forecast still works without HA at all.
exec uvicorn app.main:app \
  --app-dir /app/backend \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips='*'
