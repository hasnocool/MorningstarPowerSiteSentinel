# Roadmap

## v0.1 — local site sentinel ✅

- live Morningstar system adapter, health/observability, deterministic rules, incidents, explanations, web console, Docker/systemd

## v0.2 — flight recorder / historical diagnostics ✅

- controller history coverage/gap reconciliation
- recovered/partial/missing controller-day diagnostics
- daily controller-counter vs bounded local-energy comparisons with evidence-quality gates
- unified communications/charge/fault/alarm/history/energy/incident timeline
- conservative communication-recovery derivation
- separate historical polling/cache and flight-recorder UI summary

## v0.3 — predictive maintenance

- production, voltage sag/recovery, temperatures, communications reliability, conversion residual, charge-stage duration, and energy-discrepancy baselines
- seasonal/time-of-day baselines with explicit confidence and minimum-data requirements
- evidence-backed change-point detection

## v0.4 — federation

- optional compact multi-site health/incident federation; raw high-frequency data remains local by default
