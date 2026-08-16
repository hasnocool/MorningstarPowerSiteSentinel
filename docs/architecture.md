# Architecture

PowerSite Sentinel sits above MorningstarModbusAPI and does not duplicate its Modbus or history implementation.

MorningstarModbusAPI owns controller identity, connection reconciliation, register semantics, raw/retained history, gap reconciliation, component topology, power flow, energy-ledger provenance, and bounded local energy integration. Sentinel adds live health, controller-day continuity diagnostics, controller/local energy comparison, evidence-gated incidents, and a unified forensic timeline.

## Two monitoring cadences

Live health remains fast. Historical analysis runs on a separate slower loop (five minutes by default) and cache so a 15-second dashboard refresh does not repeatedly issue all controller history queries.

## Evidence policy

Unknown remains unknown. Recovered daily history is not reconstructed intra-day telemetry. Controller-reported and locally integrated energy stay separate. A discrepancy is diagnostic evidence, not an assertion either source is wrong. Incident resolution requires positive evidence rather than mere disappearance of the triggering signal.
