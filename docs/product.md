# Product definition

PowerSite Sentinel is a local-first flight recorder and diagnostic console for off-grid/DC power sites.

## v0.2 capabilities

The v0.1 live sentinel remains intact and v0.2 adds controller history continuity, recovered/partial/missing gap states, controller-vs-local energy reconciliation with coverage gates, a unified communications/charge/fault/alarm/history/energy/incident timeline, conservative reconnect inference, evidence-gated historical incidents, and a 30-day flight-recorder UI summary.

## Product boundary

Sentinel remains observational. It does not configure controllers, change charge profiles, trigger equalization, operate relays, start/stop generators, perform SNMP SET, or expose arbitrary Modbus writes. It also avoids forensic overclaiming: recovered daily records are not synthetic high-frequency samples, and energy discrepancies are not automatically proof of bad hardware or bad counters.
