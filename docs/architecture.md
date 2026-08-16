# Architecture

PowerSite Sentinel sits above MorningstarModbusAPI rather than duplicating its Modbus implementation.

```text
Morningstar controllers / ReadyEdge / GenStar / ReadyBlocks
                         |
                         v
                MorningstarModbusAPI
         identity + telemetry + history + provenance
                         |
               read-only HTTP system API
                         |
                         v
                PowerSite Sentinel
       +-----------------+------------------+
       |                 |                  |
  site adapter      rule engine       incident store
       |                 |                  |
       +-----------------+------------------+
                         |
             health + explanation API
                         |
                         v
                 local site-first UI
```

## Boundaries

Sentinel does not poll Modbus devices directly in v0.1. The upstream API owns physical controller identity,
connection reconciliation, register/catalog semantics, retained history, component topology, power flow, and
energy-ledger provenance.

Sentinel adds a second-order operational model:

- deterministic findings from already-normalized site telemetry;
- a health score that does not punish missing instrumentation as if it were a fault;
- a separate observability score;
- persistent incident open/resolved lifecycle;
- plain-language explanation of current power flow and priority findings.

## Evidence policy

The rule engine is intentionally conservative. An upstream measurement conflict becomes a Sentinel finding; it is
not averaged away. Unknown battery/load/generator measurements remain unknown. Derived power is displayed only when
the upstream API already supplies the derivation and its formula/provenance.
