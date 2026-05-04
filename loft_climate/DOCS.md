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
| `log_level` | Standard log level. Default `info`. |

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
