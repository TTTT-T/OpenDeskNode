# OpenDeskNode

**OpenDeskNode is an open-source platform for building compact, always-on smart displays with real-time data, voice, and AI.**

**v0.1.0 — Stock Dashboard** turns the Waveshare ESP32-S3-RLCD-4.2 into a self-hosted real-time A-share stock dashboard with a low-power monochrome display client and a LAN Stock Gateway.

The Waveshare ESP32-S3-RLCD-4.2 is the first validated reference hardware, not a permanent platform restriction. OpenDeskNode is designed so that additional display boards, MCUs, edge-computing devices, local peripherals, and services can be added over time.

## What v0.1.0 includes

- Four-stock A-share dashboard with Chinese names, price, change, percentage,
  market state, and intraday sparklines.
- Approximately 10-second device polling with a last-good snapshot and a
  five-minute failure grace period.
- Self-hosted FastAPI/SQLite Stock Gateway with a mobile-friendly watchlist
  page and versioned JSON API.
- Provider isolation: market-data credentials and provider-specific formats
  remain on the server; the display node only talks to its configured Gateway.
- Monochrome-friendly 2x2 layout validated on the reference RLCD hardware.

## Architecture

```text
display node -- LAN HTTP/schema v1 --> Stock Gateway --> market-data providers
     |                                  |
     +-- local UI and last-good state   +-- watchlist, cache, SQLite, web UI
```

The product firmware lives in `firmware/product/`. The Gateway lives in
`gateway/`. The frozen `firmware/xiaozhi/` tree is an attributed hardware
reference only and is not a runtime or build dependency of OpenDeskNode.

## Quick start: Stock Gateway

Requirements: Docker with Compose support.

```bash
cp .env.example .env
# Set STOCK_GATEWAY_PUBLIC_HOSTNAME to the host name or LAN IP reachable by the node.
docker compose up -d --build
curl --fail http://127.0.0.1:8000/healthz
```

Open `http://<gateway-host>:8000/` to manage the four-stock watchlist. Keep the
service on a trusted LAN; v0.1.0 does not provide authentication and is not
intended for direct Internet exposure.

## Build the reference firmware

Requirements: macOS or Linux, Git, and enough disk space for ESP-IDF v6.0.2.

```bash
bash scripts/setup-idf.sh
bash scripts/build-clean-firmware.sh
```

Configure `OpenDeskNode > Stock Gateway URL` with `idf.py menuconfig` before
building if the default host is not reachable from the device. Wi-Fi credentials
are provisioned at runtime and must never be committed or compiled into the
firmware.

The build script writes generated output outside the repository by default.
A successful build does not replace device-level validation of display, Wi-Fi,
flash layout, and stability.

## Verification

```bash
bash scripts/verify-public-release.sh
bash scripts/verify-phase-1d.sh
bash scripts/verify-phase-1e.sh
```

The verifier names retain internal development identifiers for traceability;
the public product version is **OpenDeskNode v0.1.0 — Stock Dashboard**.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Product requirements](docs/PRODUCT_REQUIREMENTS.md)
- [Reference hardware baseline](docs/HARDWARE_BASELINE.md)
- [Stock Gateway deployment](docs/NAS_STOCK_GATEWAY.md)

## Security and secrets

- Do not commit `.env`, database files, logs, Wi-Fi credentials, API keys, or
  provider tokens.
- Keep the unauthenticated Gateway on a trusted LAN.
- The default provider combination uses public endpoints and does not require
  the placeholder API credentials in `.env.example`.

## License

OpenDeskNode's original code and documentation are released under the
[Apache License 2.0](LICENSE). Bundled reference code, generated fonts, and external
dependencies retain their respective licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
