# PowerSite Sentinel agent guide

## Product contract

PowerSite Sentinel is a local-first, read-only observability and diagnostics layer above MorningstarModbusAPI.

- Treat MorningstarModbusAPI as the hardware, identity, telemetry, component-graph, and provenance source of truth.
- Never add Modbus/SNMP/controller write paths to Sentinel.
- Never reinterpret an upstream `unknown` value as zero.
- Preserve upstream `observed`, `derived`, `unknown`, `quality`, `sources`, and conflict semantics.
- Deterministic rules must explain the evidence and threshold that triggered them.
- Keep health and observability separate: missing sensors reduce visibility, not necessarily physical health.
- Incident fingerprints must be stable enough to deduplicate recurring evaluations.
- New vendor integrations belong behind adapters; do not contaminate the core site model with product-specific register logic.

## Validation

Before publishing changes run:

```bash
python -m compileall -q src
pytest -q
ruff check .
```
