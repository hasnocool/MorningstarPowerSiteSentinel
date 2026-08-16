# Product definition

PowerSite Sentinel is a local-first flight recorder and diagnostic console for off-grid/DC power sites.

## User question

The primary question is not "what is register 0x001B?" It is:

> Is this power site healthy, what is happening now, what changed, and what evidence supports that conclusion?

## v0.1 capabilities

- discover sites from `/v1/systems`;
- collect current site/controller/component/power/energy context from MorningstarModbusAPI;
- score communications, freshness, and evidence-backed operational state;
- score observability independently from health;
- detect stale telemetry, offline/degraded controllers, measurement conflicts, large DC power-balance residuals,
  and low reported SOC using configurable thresholds;
- persist warning/critical incidents and resolve them automatically when the triggering evidence disappears;
- explain the current site in plain language without inventing unavailable values;
- serve a small local site-first web console;
- operate without cloud connectivity.

## Non-goals for v0.1

- controller configuration or remote control;
- generator start/stop;
- charge-profile changes;
- write-capable Modbus or SNMP operations;
- black-box machine-learning alarms;
- claiming battery health/capacity from insufficient telemetry.
