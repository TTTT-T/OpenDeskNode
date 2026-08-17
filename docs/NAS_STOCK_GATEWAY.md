# Stock Gateway deployment

OpenDeskNode's Stock Gateway is a Python 3.11/FastAPI service packaged for
Docker Compose. It keeps watchlists and the latest snapshots in SQLite and is
intended to run on a trusted LAN host such as a NAS, home server, or small PC.

## Network boundary

The container listens on port `8000`; the host port is controlled by
`STOCK_GATEWAY_PORT`. The service does not implement authentication or mDNS.
Do not expose it directly to the Internet. Configure your own LAN DNS, static
DHCP entry, or host IP, for example:

```text
http://stock-gateway.local:8000/
http://gateway-host.local:8000/
```

## Deploy

```bash
cp .env.example .env
# Edit the host name, port, or data location for your environment.
docker compose build
docker compose up -d
docker compose ps
```

The default named volume is `stock_gateway_data`, mounted at `/data` in the
container. The process runs as non-root UID `10001`. If you choose a bind mount
instead, create a project-owned directory and grant that UID access; do not run
the container as root merely to bypass host permissions.

## Verify

```bash
curl --fail http://127.0.0.1:${STOCK_GATEWAY_PORT:-8000}/healthz
curl --fail http://stock-gateway.local:${STOCK_GATEWAY_PORT:-8000}/api/v1/dashboard/device-a
```

Then open the root page in a browser, confirm the four-slot watchlist, save a
known symbol order, restart only this container, and verify that the order is
still present. The default provider combination uses public endpoints and does
not consume the placeholder keys in `.env.example`.

## Back up

Stop only the Stock Gateway container, then back up
`/data/stock-gateway.sqlite3` and `/data/logs/stock-gateway.log*`. Preserve
unrelated host and container data. The service keeps current snapshots, not a
long-term historical market database.

## Known v0.1.0 limits

- LAN-only and unauthenticated.
- Provider availability and market-session behavior depend on external data
  sources.
- Whole-host restart and long-running behavior must be validated in each
  deployment environment.
