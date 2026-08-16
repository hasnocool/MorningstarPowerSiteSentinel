# Sentinel API

The local Sentinel API is separate from MorningstarModbusAPI and contains only local observability/diagnostic
resources.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Sentinel and upstream Morningstar API reachability |
| `GET /v1/sites` | Upstream system/site inventory |
| `GET /v1/sites/{site_uid}/assessment` | Full current snapshot, health, findings, and open incidents |
| `GET /v1/sites/{site_uid}/explain` | Plain-language evidence-backed site explanation |
| `GET /v1/sites/{site_uid}/incidents` | Incident history for one site |
| `GET /v1/incidents` | Cross-site local incident history |

No endpoint writes to a Morningstar controller.
