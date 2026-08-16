# Roadmap

## v0.1 — local site sentinel

- Morningstar system adapter
- deterministic health/anomaly rules
- health vs observability scoring
- incident persistence
- explanation API
- local web console
- Docker/systemd deployment

## v0.2 — historical diagnostics

- consume controller history coverage/gap reconciliation endpoints
- incident timeline merged with upstream alarms/faults/reconnects/charge-state changes
- daily energy-counter vs locally integrated-energy discrepancy checks
- configurable quiet periods and alert routing

## v0.3 — predictive maintenance

- trend baselines for production, voltage sag/recovery, controller temperatures, communications reliability,
  conversion residuals, and charge-stage duration
- seasonal/time-of-day baselines with explicit confidence and minimum-data requirements

## v0.4 — federation

- multiple edge Sentinels reporting compact normalized health summaries to an optional central fleet service
- raw high-frequency data remains local by default

## Future adapters

Keep the core component model vendor-neutral so BMS, inverter, AC meter, weather, generator-telemetry, and other
read-only adapters can feed the same source/storage/load/converter/meter/environment roles.
