# PowerSite Sentinel agent guide

## Product contract

PowerSite Sentinel is a local-first, read-only observability and diagnostics layer above MorningstarModbusAPI.

- Treat MorningstarModbusAPI as the hardware, identity, telemetry, history-reconciliation, component-graph, and provenance source of truth.
- Never add Modbus/SNMP/controller write paths to Sentinel.
- Never reinterpret an upstream `unknown` value as zero.
- Preserve upstream `observed`, `derived`, `unknown`, `quality`, `sources`, and conflict semantics.
- Never reconstruct missing high-frequency samples from controller-retained daily records.
- Keep controller-reported energy and locally integrated energy as separate evidence classes.
- Treat an energy discrepancy as diagnostic evidence, not proof that either source is wrong.
- Require adequate local integration coverage before making energy-discrepancy findings actionable.
- Do not resolve an incident merely because the evidence disappeared; require current evidence that can clear it.
- Deterministic rules and derived timeline events must explain the evidence and threshold/inference that triggered them.
- Keep health and observability separate: missing sensors reduce visibility, not necessarily physical health.
- Incident fingerprints must be stable enough to deduplicate recurring evaluations.
- New vendor integrations belong behind adapters; do not contaminate the core site model with register-specific logic.

## Validation

Before publishing changes run:

```bash
python -m compileall -q src
pytest -q
ruff check .
```
