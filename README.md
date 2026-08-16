# Morningstar PowerSite Sentinel

**PowerSite Sentinel** is a local-first observability, diagnostics, and incident-intelligence product for Morningstar power systems. It sits above [`MorningstarModbusAPI`](https://github.com/hasnocool/MorningstarModbusAPI) and answers: **Is my power site healthy, what happened, when did it change, and what evidence supports that conclusion?**

Sentinel is intentionally read-only. MorningstarModbusAPI remains the source of truth for hardware discovery, physical controller identity, Modbus decoding, raw/retained history, component relationships, power-flow provenance, and energy accounting.

## v0.2 flight-recorder foundation

v0.2 keeps the v0.1 live sentinel and adds:

- controller history continuity from the API's coverage/gap reconciliation endpoints;
- explicit `recovered`, `partial`, and `missing` controller-day states;
- controller-retained energy vs gap-bounded local integration as separate evidence classes;
- minimum local-integration coverage before energy discrepancies become actionable;
- a unified forensic timeline for communications, charge stages, alarms, faults, history synchronization/gaps, energy discrepancies, and Sentinel incidents;
- conservative evidence-backed `COMMUNICATION_RECOVERED` derivation;
- evidence-gated incident resolution;
- a separate slower forensic monitor/cache so 15-second live monitoring remains lightweight;
- a 30-day flight-recorder summary in the local web UI.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Sentinel version plus Morningstar API reachability |
| `GET /v1/sites` | Site inventory |
| `GET /v1/sites/{site_uid}/assessment` | Current live assessment |
| `GET /v1/sites/{site_uid}/explain` | Evidence-backed current explanation |
| `GET /v1/sites/{site_uid}/forensics` | Coverage/gaps, energy reconciliation, findings/incidents, unified timeline |
| `GET /v1/sites/{site_uid}/timeline` | Filtered forensic timeline |
| `GET /v1/sites/{site_uid}/incidents` | Site incident history |
| `GET /v1/incidents` | Cross-site incident history |

## Forensic evidence rules

- A recovered day improves day-level evidence coverage; it does not reconstruct intra-day samples.
- `controller_reported_wh` and `integrated_output_wh` remain independent measurements.
- Sentinel requires sufficient accepted local integration time before raising energy-discrepancy incidents.
- A discrepancy is diagnostic evidence, not automatic proof either source is wrong.
- An incident resolves only when current evidence can demonstrate the triggering condition cleared.

See [`docs/forensics.md`](docs/forensics.md), [`docs/api.md`](docs/api.md), and [`docs/architecture.md`](docs/architecture.md).

## Quick start

Start MorningstarModbusAPI first, normally on `127.0.0.1:8080`. Use `run` when the same process should both poll the
controller and serve the HTTP API Sentinel consumes:

```bash
morningstar-modbus --config /path/to/morningstar-config.toml run
```

Verify the upstream service before starting Sentinel:

```bash
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:8080/v1/systems
```

Then start Sentinel:

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

Sentinel retries connection-level upstream failures and retains the last-known-good site inventory/assessment in
memory so a short MorningstarModbusAPI restart does not immediately erase the site view. `/health` still reports the
upstream as unreachable while stale data is being shown.

## Configuration

```toml
[morningstar]
base_url = "http://127.0.0.1:8080"
timeout_seconds = 5.0
connect_attempts = 5
retry_backoff_seconds = 0.25

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
- `SENTINEL_MORNINGSTAR_CONNECT_ATTEMPTS`
- `SENTINEL_MORNINGSTAR_RETRY_BACKOFF`
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
| `GET /v1/sites/{site_uid}/forensics` | Forensic history report with coverage gaps and timeline |
| `GET /v1/sites/{site_uid}/timeline` | Unified provenance-backed forensic timeline |
| `GET /v1/controllers/{controller_uid}/detail` | Rich lazy-loaded controller detail |
| `GET /v1/sites/{site_uid}/incidents` | Local incident history for a site |
| `GET /v1/incidents` | Local incident history across sites |

## Safety contract

Sentinel does **not** configure controllers or expose Modbus writes, SNMP SET, equalization, charge-profile changes, generator start/stop, relay control, reset operations, or arbitrary write-capable passthrough.

## Development

```bash
python -m pip install -e '.[dev]'
python -m compileall -q src
pytest -q
ruff check .
```

## License

MIT
