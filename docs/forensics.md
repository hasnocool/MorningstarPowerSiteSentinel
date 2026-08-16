# Flight recorder and forensic diagnostics

PowerSite Sentinel v0.2 adds a historical forensic layer above MorningstarModbusAPI. It consumes the API's controller-scoped reconciliation products rather than rebuilding history from raw registers.

## Evidence sources

For each immutable `controller_uid`, Sentinel reads history coverage, history gaps, daily energy, and energy summary endpoints, plus the system event stream.

A recovered day means a complete controller-retained daily record exists despite no persisted local poll sample. It does **not** mean missing high-frequency samples were reconstructed.

## Continuity states

- `recovered`: no persisted poll samples, complete retained daily evidence exists.
- `partial`: no persisted poll samples, retained daily evidence is incomplete.
- `missing`: neither persisted polling nor adequate retained daily evidence exists.

The site summary reports controller-days rather than pretending a multi-controller site has one homogeneous history stream.

## Energy reconciliation

`controller_reported_wh` and `integrated_output_wh` are independent evidence classes. Sentinel never adds them together and never substitutes one for the other. A daily discrepancy becomes actionable only when the accepted local integration covers at least `energy_min_integrated_seconds` (six hours by default). Sparse integration is reported as `insufficient_local_coverage` even if the arithmetic difference is large.

A large difference can reflect persistence gaps, skipped intervals, sampling bias, counter resolution, or a real measurement problem. Sentinel treats it as diagnostic evidence, not proof either source is wrong.

## Unified timeline

The timeline preserves upstream communications, charge-stage, fault/alarm, and history-sync events, then adds explicitly labeled Sentinel-derived gap, energy, reconnect, and incident-lifecycle entries. A communication recovery is derived only when a later successful observation or current controller connection metadata proves recovery after a recorded error.

## Incident resolution

Historical incidents use evidence-gated resolution. If comparative evidence disappears, Sentinel keeps the incident open rather than interpreting unknown as cleared.

## Scheduling

Live health and historical forensics use separate cadences. The forensic loop defaults to five minutes and has its own cache so normal live dashboard refreshes do not issue the full historical query set.
