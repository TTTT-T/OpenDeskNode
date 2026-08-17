# Changelog

## v0.1.0 — Stock Dashboard

Initial public release of OpenDeskNode.

### Included

- Four-stock A-share dashboard for the Waveshare ESP32-S3-RLCD-4.2 reference
  hardware.
- Self-hosted LAN Stock Gateway with FastAPI, SQLite persistence, a mobile
  watchlist UI, and versioned dashboard API.
- Approximately 10-second polling, strict schema parsing, last-good retention,
  market-session states, and intraday sparklines.
- Reproducible ESP-IDF v6.0.2 setup, host-side tests, Gateway tests, and Docker
  deployment files.

### Known limits

- The Gateway is LAN-only and unauthenticated; do not expose it directly to
  the Internet.
- The validated reference firmware targets the Waveshare board above; other
  display nodes require a platform port.
- Trading-session live progression, unusual market states, whole-host restart,
  and cross-day stability remain environment-dependent validation areas.
