# Desk Dashboard

Multi-widget desk dashboard for iPad. Sibling to the Loft Climate Add-on —
climate becomes one tile among four (stock tracker, calendar, Pi health).

## Configuration

| Option | Type | Description |
|---|---|---|
| `loft_internal_url` | str | URL for the loft climate Add-on. Default `http://local_loft_climate:8000` (HA Supervisor's per-Add-on DNS). |
| `ical_url` | password | iCloud or Google iCal share link (read-only). Mask is for UI display only. |
| `log_level` | enum | uvicorn log level (info/debug/warning). |

## First-run setup

1. Install + start the Add-on. The dashboard becomes available on the Pi at `http://<pi>:8001`.
2. Add a Cloudflare Tunnel ingress rule routing `desk.harrymorris.me → http://localhost:8001`.
3. Add a Cloudflare Access application for `desk.harrymorris.me` reusing the same Google OAuth policy as `loft.harrymorris.me`.
4. Open the URL in Safari on iPad, log in once via Google, **Add to Home Screen**.

## Widgets

- **Climate** — summary tile. Tap opens `loft.harrymorris.me` in a new tab (full PWA).
- **Stock** — LQQ3.L price + day change + sparkline. SQLite-backed stale cache when yfinance fails.
- **Calendar** — next event from the configured iCal URL.
- **System** — CPU temp, disk %, internet uptime aggregated from 3-target ping rotation (1.1.1.1, 8.8.8.8, gateway).

## Architecture notes

Climate widget proxies the loft_climate Add-on via the HA Supervisor's
internal DNS (`local_loft_climate`). No CF Access hop on the
server-to-server call. If the climate Add-on is stopped, the climate tile
shows a "stale" badge — by design.

Background `MonitorTask` records uptime samples to SQLite every 30s. The
supervisor pattern guarantees the task survives uncaught exceptions
(DNS flakes, network drops): an outer loop catches + retries after 5s.
