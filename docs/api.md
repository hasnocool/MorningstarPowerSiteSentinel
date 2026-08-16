# Sentinel API

The Sentinel API is read-only.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Sentinel/upstream reachability |
| `GET /v1/sites` | Site inventory |
| `GET /v1/sites/{site_uid}/assessment` | Current live assessment |
| `GET /v1/sites/{site_uid}/explain` | Current evidence-backed explanation |
| `GET /v1/sites/{site_uid}/forensics` | Historical continuity, energy reconciliation, findings/incidents, timeline |
| `GET /v1/sites/{site_uid}/timeline` | Filtered unified forensic timeline |
| `GET /v1/sites/{site_uid}/incidents` | Site incident history |
| `GET /v1/incidents` | Cross-site incident history |

`/forensics` supports `days=1..366`, `max_gap_seconds=1..3600`, `event_limit=1..5000`, and `refresh=true`. `/timeline` supports the same window/gap controls plus `limit` and categories `communications`, `charge`, `fault`, `alarm`, `history`, `energy`, `incident`, and `system`.

No endpoint writes to a controller and no historical endpoint reconstructs missing high-frequency telemetry.
