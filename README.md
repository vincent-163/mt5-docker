# MT5 on Wine (Docker)

Run MetaTrader 5 inside a Docker container with an rpyc bridge for programmatic access from Linux.

No prebuilt Wine prefix or `servers.dat` needed — everything is downloaded and installed during `docker build`.

## What's Inside

- **Wine 10.0** (Kron4ek PE-only build) — Wine 11.x is broken for MT5 (anti-debug check)
- **MetaTrader 5** installed via official `mt5setup.exe`
- **Python 3.9** (embeddable) with MetaTrader5, rpyc, numpy, pywin32
- **rpyc server** on TCP port 18812 exposing MT5 functions to Linux clients
- **Xvfb** virtual display (MT5 requires a GUI)
- MQL5 files pre-compiled during build (avoids 60s IPC timeout on first run)

## Prerequisites

- Docker

## Prebuilt Image

A prebuilt image is available on GHCR:

```bash
docker pull ghcr.io/vincent-163/mt5-docker:latest
```

Skip to [Run](#run) if using the prebuilt image — no build step needed.

## Build

Building from source requires internet access from Docker. If containers can't reach the internet directly, set `BUILD_PROXY`.

```bash
# Direct internet access
./build_and_run.sh build

# With proxy
BUILD_PROXY=http://172.17.0.1:8080 ./build_and_run.sh build
```

Build takes ~10 minutes (downloads Wine ~62MB, MT5 ~23MB, Python packages ~27MB, plus MQL5 warmup).

## Run

```bash
# Start container
MT5_PROXY_ADDRESS=172.17.0.1:8080 \
MT5_LOGIN=<your_login> \
MT5_PASSWORD='<your_password>' \
MT5_SERVER='<broker_ip:port>' \
./build_and_run.sh run
```

Environment variables:

| Variable | Description |
|---|---|
| `MT5_PROXY_ADDRESS` | HTTP proxy for MT5 broker connection (host:port) |
| `MT5_LOGIN` | MT5 account number |
| `MT5_PASSWORD` | MT5 account password |
| `MT5_SERVER` | Broker server — either name (`BrokerName-Live`) or direct IP (`1.2.3.4:443`) |

Using a direct IP for `MT5_SERVER` avoids needing `servers.dat` (which maps broker names to IPs).

## Test

```bash
# Install rpyc on host (if not already)
pip install rpyc

# Run test client
python3 mt5_client.py <login> <password> <server>

# Example
python3 mt5_client.py <login> '<password>' '<server_ip:port>'
```

## Other Commands

```bash
./build_and_run.sh logs    # Tail container logs
./build_and_run.sh stop    # Stop and remove container
```

## Using from Python

```python
import rpyc

conn = rpyc.connect("127.0.0.1", 18812, config={"sync_request_timeout": 240})
mt5 = conn.root

# Initialize (launches terminal + IPC connection)
mt5.initialize(
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    login=12345678,
    password="your_password",
    server="broker_ip:443"
)

# Query account
info = mt5.account_info()
print(info["balance"], info["equity"])

# Get symbols
print(mt5.symbols_total())

# Cleanup
mt5.shutdown()
conn.close()
```

## Available rpyc Methods

`initialize`, `shutdown`, `login`, `last_error`, `version`, `account_info`, `terminal_info`, `symbols_total`, `symbols_get`, `symbol_info`, `symbol_info_tick`, `symbol_select`, `copy_rates_from`, `copy_rates_from_pos`, `copy_rates_range`, `copy_ticks_from`, `copy_ticks_range`, `orders_total`, `orders_get`, `positions_total`, `positions_get`, `history_orders_total`, `history_orders_get`, `history_deals_total`, `history_deals_get`, `order_send`, `order_check`, `order_calc_margin`, `order_calc_profit`

## Notes

- The MT5 installer downloads files from MetaQuotes CDN during build, so a proxy (or direct internet) is required at build time.
- Wine 10.0 spawns many `explorer.exe` processes over time. The entrypoint runs a reaper that culls them every 10s.
- `initialize()` requires credentials — calling it without login/password always times out.
- The `[Experts] Enabled` flag resets to 0 when the account changes. The rpyc server handles this by writing `common.ini` before each `initialize()`.

## Docker Host

If `docker` isn't accessible at the default socket, set `DOCKER_HOST`:

```bash
export DOCKER_HOST=unix:///run/docker.sock
```
