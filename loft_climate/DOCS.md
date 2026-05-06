# Loft Climate Dashboard

Smart climate control for a SW-facing London loft. Recommends per-zone blind
positions and window open/closed states based on indoor sensors, outdoor weather,
sun position, and a configurable rule engine.

## Configuration

| Option | Description |
|--------|-------------|
| `owm_api_key` | OpenWeatherMap API key with [One Call 3.0](https://openweathermap.org/api/one-call-3) access (free tier — 1000 calls/day). |
| `ha_token` | A long-lived access token for Home Assistant. Create one at *Profile → Security → Long-Lived Access Tokens*. |
| `ha_entity_map` | JSON object mapping zone IDs to their HA entity IDs. See below. |
| `ha_outdoor_entities` | JSON object mapping outdoor sensor entities. See below. |
| `ha_sunshine_entity` | Entity ID of the SW glazing lux sensor (e.g. Aqara Light Sensor T1). When set, replaces the manual 0-5 sunshine scale. |
| `vapid_subject` | Identity for VAPID claims (`mailto:` URL or `https:` URL). Default `mailto:harrymorris22@gmail.com`. |
| `notify_email_smtp_password` | Optional Gmail app password used to send a fallback email when an iPhone subscription is detected as stale (>7 days no successful push). |
| `notify_email_to` | Optional override for the staleness-email recipient. Defaults to the email portion of `vapid_subject`. |
| `log_level` | Standard log level. Default `info`. |

## Push notifications (v0.3.0+)

The Add-on includes a Web Push subsystem that pings your iPhone when the
engine wants you to act, even when the dashboard isn't open.

**iPhone setup:**
1. Open `https://loft.harrymorris.me` in Safari (signed in via Cloudflare Access).
2. Tap **Share → Add to Home Screen**.
3. Open the new icon (PWA standalone window).
4. Navigate to `Notifications` → tap **Enable notifications** → Allow.
5. Tap **Send test push** to verify delivery.

**Trigger model:**
- RED urgency anywhere → push always (incl. quiet hours)
- AMBER actions due within 15 min → push during waking hours
- Scenario green→amber transitions → push during waking hours
- Quiet hours default 23:00–07:00 (configurable via `/config`)
- 30-min cooldown per `(actuator, scenario)`

**Snooze:** the `/notifications` page has Snooze 2h / Snooze until 07:00 / Resume.

### `ha_entity_map` format

```json
{
  "downstairs": {
    "temp": "sensor.lumi_lumi_weather_temperature",
    "humidity": "sensor.lumi_lumi_weather_humidity"
  },
  "bedroom": {
    "temp": "sensor.bedroom_aqara_temperature",
    "humidity": "sensor.bedroom_aqara_humidity"
  }
}
```

Valid zone IDs: `mezzanine`, `downstairs`, `ceiling_apex`, `bedroom`. Any zone
without a mapping falls back to whatever the dashboard's manual-entry form has
last submitted.

### `ha_outdoor_entities` format

```json
{
  "temp": "sensor.indoor_outdoor_meter_6d73_temperature",
  "humidity": "sensor.indoor_outdoor_meter_6d73_humidity"
}
```

When present, the dashboard uses these readings instead of OpenWeatherMap's
forecast for the *current* outdoor temperature + humidity. OWM still provides
wind, cloud cover, UV, sunrise/sunset, and the hourly forecast.

## Networking

The Add-on runs on host network and listens on **port 8000**. After starting,
the dashboard is reachable at:

- `http://homeassistant.local:8000` (LAN)
- `http://<pi-ip>:8000`

For internet access (anywhere in the world, behind Google login), pair this
Add-on with the **Cloudflare Tunnel** Add-on and configure a Cloudflare Access
policy on the chosen hostname.

## Persistent state

The Add-on stores its SQLite database (`climate.db`) and live config
(`config.json`) under `/data` inside the container, which HA persists across
restarts and updates.

## Project layout

This Add-on is the production deployment of the project at
[github.com/harrymorris22/home-dashboard](https://github.com/harrymorris22/home-dashboard).
The dev environment (Vite + uvicorn `--reload`) lives in the same repo under
`loft_climate/{backend,frontend}/`.
