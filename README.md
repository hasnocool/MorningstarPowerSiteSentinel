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

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp config.example.toml config.toml
powersite-sentinel --config config.toml serve
```

Open `http://127.0.0.1:8090/`; API docs are at `http://127.0.0.1:8090/docs`.

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
