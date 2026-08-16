# Morningstar PowerSite Sentinel

**PowerSite Sentinel** is a local-first observability, diagnostics, and incident-intelligence product for Morningstar
power systems. It sits above
[`MorningstarModbusAPI`](https://github.com/hasnocool/MorningstarModbusAPI) and answers a different question than a
register dashboard:

> **Is my power site healthy, what is happening now, what changed, and what evidence supports that conclusion?**

Sentinel is intentionally read-only. MorningstarModbusAPI remains the source of truth for hardware discovery,
physical controller identity, Modbus decoding, history, component relationships, power-flow provenance, and energy
accounting. Sentinel consumes those normalized resources and adds explainable site health, anomaly detection,
incident lifecycle, and an end-user site view.

## v0.1 product foundation

The initial product includes:

- **site-first monitoring** from the upstream `/v1/systems` API rather than one raw endpoint at a time;
- **evidence-backed health scoring** for communications, telemetry freshness, and operational findings;
- a separate **observability score**, so missing shunts/sensors do not masquerade as physical failures;
- deterministic detection of:
  - stale site telemetry;
  - offline/degraded controllers;
  - conflicting whole-system measurements;
  - large source-backed DC power-balance residuals;
  - low reported battery SOC against configurable thresholds;
- **persistent incidents** with automatic open/update/resolve lifecycle;
- **plain-language explanations** of live solar/load/battery flow and priority findings;
- a small **local web console** served directly by Sentinel;
- local SQLite incident storage;
- Python, Docker, and systemd deployment paths;
- CI across Python 3.12, 3.13, and 3.14.

## Architecture

```text
Morningstar hardware
       |
       v
MorningstarModbusAPI
 discovery / identity / catalog / telemetry / history
 systems / components / power flow / energy ledger
       |
       | read-only HTTP
       v
MorningstarPowerSiteSentinel
 adapter -> rules -> health -> incidents -> explanation
       |
       +---- REST API
       `---- local site-first web UI
```

Sentinel never converts an upstream `unknown` measurement to zero and never averages away an upstream measurement
conflict. Health and observability are deliberately separate concepts.

## Quick start

Start MorningstarModbusAPI first, normally on `127.0.0.1:8080`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp config.example.toml config.toml
powersite-sentinel --config config.toml serve
```

Then open:

```text
http://127.0.0.1:8090/
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8090/docs
```

## Configuration

```toml
[morningstar]
base_url = "http://127.0.0.1:8080"
timeout_seconds = 5.0

[sentinel]
database_path = "./data/sentinel.db"
poll_interval_seconds = 15.0
monitor_enabled = true
stale_after_seconds = 45.0
residual_warning_w = 50.0
residual_warning_percent = 8.0
residual_critical_percent = 20.0
soc_warning_percent = 30.0
soc_critical_percent = 15.0

[server]
host = "127.0.0.1"
port = 8090
```

Environment overrides are available for the common appliance settings:

- `SENTINEL_MORNINGSTAR_URL`
- `SENTINEL_DATABASE_PATH`
- `SENTINEL_POLL_INTERVAL`
- `SENTINEL_HOST`
- `SENTINEL_PORT`

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Sentinel version plus Morningstar API reachability |
| `GET /v1/sites` | Site inventory from MorningstarModbusAPI |
| `GET /v1/sites/{site_uid}/assessment` | Snapshot + health + findings + open incidents |
| `GET /v1/sites/{site_uid}/explain` | Plain-language evidence-backed explanation |
| `GET /v1/sites/{site_uid}/incidents` | Local incident history for a site |
| `GET /v1/incidents` | Local incident history across sites |

## Safety contract

PowerSite Sentinel does **not** configure controllers. It does not expose Modbus writes, SNMP SET, equalization,
charge-profile changes, generator start/stop, relay control, reset operations, or arbitrary passthrough commands.

The first product deliberately earns trust as a flight recorder and diagnostic system before any future control
surface is considered.

## Development

```bash
python -m pip install -e '.[dev]'
python -m compileall -q src
pytest -q
ruff check .
```

## Documentation

- [`docs/product.md`](docs/product.md) — product contract, v0.1 scope, and non-goals
- [`docs/architecture.md`](docs/architecture.md) — system boundaries and evidence policy
- [`docs/api.md`](docs/api.md) — Sentinel HTTP surface
- [`docs/deployment.md`](docs/deployment.md) — Python, Docker, and systemd deployment
- [`docs/roadmap.md`](docs/roadmap.md) — historical diagnostics, predictive maintenance, and fleet federation

## License

MIT
