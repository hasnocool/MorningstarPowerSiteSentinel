"""Unified provenance-rich forensic timeline for PowerSite Sentinel."""

from __future__ import annotations

from datetime import UTC, datetime


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _controller_uid(controller: dict[str, object]) -> str:
    return str(controller.get("controller_uid") or controller.get("controller_id") or "")


def _duration_days(gap: dict[str, object]) -> int:
    value = gap.get("duration_days")
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


_CHARGE_EVENTS = {
    "FLOAT_ENTERED",
    "ABSORPTION_ENTERED",
    "EQUALIZATION_ENTERED",
    "CHARGE_STATE_CHANGED",
}
_FAULT_EVENTS = {"FAULT_STARTED", "FAULT_CLEARED"}
_ALARM_EVENTS = {"ALARM_STARTED", "ALARM_CLEARED"}
_COMM_EVENTS = {"COMMUNICATION_ERROR", "COMMUNICATION_RECOVERED"}
_HISTORY_EVENTS = {"HISTORY_BACKFILL_COMPLETED", "HISTORY_BACKFILL_FAILED"}


def _event_category(event_type: str) -> str:
    if event_type in _CHARGE_EVENTS:
        return "charge"
    if event_type in _FAULT_EVENTS:
        return "fault"
    if event_type in _ALARM_EVENTS:
        return "alarm"
    if event_type in _COMM_EVENTS:
        return "communications"
    if event_type in _HISTORY_EVENTS:
        return "history"
    if event_type.startswith("HISTORY_GAP_"):
        return "history"
    if event_type.startswith("ENERGY_"):
        return "energy"
    if event_type.startswith("SENTINEL_INCIDENT_"):
        return "incident"
    return "system"


def _event_title(event_type: str) -> str:
    return event_type.replace("_", " ").title()


def _normalize_upstream_event(site_uid: str, raw: dict[str, object]) -> dict[str, object]:
    event_type = str(raw.get("event_type") or "SYSTEM_EVENT")
    return {
        "id": str(raw.get("id") or f"upstream:{event_type}:{raw.get('observed_at')}"),
        "site_uid": site_uid,
        "controller_uid": raw.get("controller_uid"),
        "observed_at": raw.get("observed_at"),
        "category": _event_category(event_type),
        "event_type": event_type,
        "severity": raw.get("severity") or "info",
        "title": _event_title(event_type),
        "message": raw.get("message") or "",
        "source": raw.get("source") or "morningstar-api",
        "provenance": ["morningstar_api_event"],
        "payload": _dict(raw.get("payload")),
    }


def _controller_recovery_time(controller: dict[str, object]) -> datetime | None:
    candidates: list[object] = [
        controller.get("last_seen"),
        controller.get("last_success"),
    ]
    lifecycle = _dict(controller.get("lifecycle"))
    candidates.extend((lifecycle.get("last_seen"), lifecycle.get("last_success")))
    parsed = [item for value in candidates if (item := _parse_time(value)) is not None]
    return max(parsed) if parsed else None


def _derive_reconnects(
    site_uid: str,
    events: list[dict[str, object]],
    controllers: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_uid: dict[str, list[dict[str, object]]] = {}
    for event in events:
        uid = str(event.get("controller_uid") or "")
        if uid:
            by_uid.setdefault(uid, []).append(event)

    controller_by_uid = {_controller_uid(item): item for item in controllers if _controller_uid(item)}
    derived: list[dict[str, object]] = []
    for uid, items in by_uid.items():
        items.sort(key=lambda item: str(item.get("observed_at") or ""))
        pending_error: dict[str, object] | None = None
        for item in items:
            event_type = str(item.get("event_type") or "")
            if event_type == "COMMUNICATION_ERROR":
                pending_error = item
                continue
            if pending_error is None:
                continue
            if item.get("source") == "live-modbus" or item.get("category") in {
                "charge",
                "fault",
                "alarm",
            }:
                derived.append(
                    {
                        "id": f"derived-reconnect:{uid}:{item.get('observed_at')}",
                        "site_uid": site_uid,
                        "controller_uid": uid,
                        "observed_at": item.get("observed_at"),
                        "category": "communications",
                        "event_type": "COMMUNICATION_RECOVERED",
                        "severity": "info",
                        "title": "Communication Recovered",
                        "message": (
                            "A successful later live observation proves communication resumed "
                            "after a recorded communication error."
                        ),
                        "source": "sentinel-derived",
                        "provenance": ["communication_error", "later_live_observation"],
                        "payload": {
                            "error_event_id": pending_error.get("id"),
                            "recovery_evidence_event_id": item.get("id"),
                        },
                    }
                )
                pending_error = None

        if pending_error is None:
            continue
        controller = controller_by_uid.get(uid, {})
        status = str(controller.get("status") or "").lower()
        recovery_at = _controller_recovery_time(controller)
        error_at = _parse_time(pending_error.get("observed_at"))
        if status == "online" and recovery_at is not None and error_at is not None and recovery_at > error_at:
            derived.append(
                {
                    "id": f"derived-reconnect:{uid}:{recovery_at.isoformat()}",
                    "site_uid": site_uid,
                    "controller_uid": uid,
                    "observed_at": recovery_at.isoformat(),
                    "category": "communications",
                    "event_type": "COMMUNICATION_RECOVERED",
                    "severity": "info",
                    "title": "Communication Recovered",
                    "message": (
                        "The controller is currently online and its later successful observation "
                        "proves recovery after the recorded communication error."
                    ),
                    "source": "sentinel-derived",
                    "provenance": ["communication_error", "controller_last_success"],
                    "payload": {"error_event_id": pending_error.get("id")},
                }
            )
    return derived


def _history_gap_events(site_uid: str, report: dict[str, object]) -> list[dict[str, object]]:
    uid = str(report.get("controller_uid") or "")
    events: list[dict[str, object]] = []
    for gap in [item for item in _list(report.get("gaps")) if isinstance(item, dict)]:
        status = str(gap.get("status") or "missing")
        days = _duration_days(gap)
        event_type = {
            "recovered": "HISTORY_GAP_RECOVERED",
            "partial": "HISTORY_GAP_PARTIAL",
            "missing": "HISTORY_GAP_MISSING",
        }.get(status, "HISTORY_GAP")
        severity = "info" if status == "recovered" else "critical" if days >= 3 else "warning"
        message = {
            "recovered": (
                "No live samples exist for this interval, but complete controller-retained daily "
                "records preserve day-level evidence. High-frequency samples were not reconstructed."
            ),
            "partial": (
                "No live samples exist and retained controller evidence is incomplete for this interval."
            ),
            "missing": (
                "Neither persisted live samples nor complete controller-retained daily evidence "
                "cover this interval."
            ),
        }.get(status, "Historical evidence gap.")
        start = str(gap.get("from") or "")
        events.append(
            {
                "id": f"history-gap:{uid}:{start}:{status}",
                "site_uid": site_uid,
                "controller_uid": uid,
                "observed_at": f"{start}T00:00:00+00:00" if start else None,
                "category": "history",
                "event_type": event_type,
                "severity": severity,
                "title": _event_title(event_type),
                "message": message,
                "source": "sentinel-derived",
                "provenance": ["history_coverage", "history_gap_reconciliation"],
                "payload": gap,
            }
        )
    return events


def _energy_events(site_uid: str, report: dict[str, object]) -> list[dict[str, object]]:
    uid = str(report.get("controller_uid") or "")
    comparisons = [
        item
        for item in _list(_dict(report.get("energy")).get("comparisons"))
        if isinstance(item, dict)
    ]
    events: list[dict[str, object]] = []
    for item in comparisons:
        status = str(item.get("status") or "")
        if status not in {"divergent", "strongly_divergent"}:
            continue
        day = str(item.get("date") or "")
        percent = _number(item.get("difference_percent"))
        controller_wh = _number(item.get("controller_reported_wh"))
        local_wh = _number(item.get("integrated_output_wh"))
        events.append(
            {
                "id": f"energy-discrepancy:{uid}:{day}",
                "site_uid": site_uid,
                "controller_uid": uid,
                "observed_at": f"{day}T23:59:59+00:00" if day else None,
                "category": "energy",
                "event_type": "ENERGY_COUNTER_DISCREPANCY",
                "severity": "critical" if status == "strongly_divergent" else "warning",
                "title": "Energy Counter Discrepancy",
                "message": (
                    f"Controller-reported energy ({controller_wh:.1f} Wh) and locally integrated "
                    f"output energy ({local_wh:.1f} Wh) differ by {percent:+.1f}%."
                    if controller_wh is not None and local_wh is not None and percent is not None
                    else "Controller-reported and locally integrated energy materially differ."
                ),
                "source": "sentinel-derived",
                "provenance": [
                    "controller_internal_logger",
                    "live_poll",
                    "bounded_local_integration",
                ],
                "payload": item,
            }
        )
    return events


def _incident_events(site_uid: str, incidents: list[dict[str, object]]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for incident in incidents:
        incident_id = str(incident.get("incident_id") or "")
        first_seen = incident.get("first_seen")
        if first_seen:
            events.append(
                {
                    "id": f"incident-opened:{incident_id}",
                    "site_uid": site_uid,
                    "controller_uid": _dict(incident.get("evidence")).get("controller_uid"),
                    "observed_at": first_seen,
                    "category": "incident",
                    "event_type": "SENTINEL_INCIDENT_OPENED",
                    "severity": incident.get("severity") or "warning",
                    "title": str(incident.get("title") or "Sentinel Incident"),
                    "message": str(incident.get("summary") or ""),
                    "source": "sentinel-incident-store",
                    "provenance": ["sentinel_incident"],
                    "payload": {
                        "incident_id": incident_id,
                        "code": incident.get("code"),
                        "fingerprint": incident.get("fingerprint"),
                    },
                }
            )
        resolved_at = incident.get("resolved_at")
        if resolved_at:
            events.append(
                {
                    "id": f"incident-resolved:{incident_id}",
                    "site_uid": site_uid,
                    "controller_uid": _dict(incident.get("evidence")).get("controller_uid"),
                    "observed_at": resolved_at,
                    "category": "incident",
                    "event_type": "SENTINEL_INCIDENT_RESOLVED",
                    "severity": "info",
                    "title": f"Resolved: {incident.get('title') or incident.get('code')}",
                    "message": "Sentinel recorded current evidence that cleared this incident.",
                    "source": "sentinel-incident-store",
                    "provenance": ["sentinel_incident"],
                    "payload": {
                        "incident_id": incident_id,
                        "code": incident.get("code"),
                        "fingerprint": incident.get("fingerprint"),
                    },
                }
            )
    return events


def build_unified_timeline(
    site_uid: str,
    upstream_events: list[dict[str, object]],
    controllers: list[dict[str, object]],
    controller_reports: list[dict[str, object]],
    incidents: list[dict[str, object]],
    *,
    limit: int,
) -> dict[str, object]:
    """Merge upstream and Sentinel forensic evidence into one provenance-rich timeline."""

    normalized = [_normalize_upstream_event(site_uid, item) for item in upstream_events]
    events = list(normalized)
    events.extend(_derive_reconnects(site_uid, normalized, controllers))
    for report in controller_reports:
        events.extend(_history_gap_events(site_uid, report))
        events.extend(_energy_events(site_uid, report))
    events.extend(_incident_events(site_uid, incidents))

    deduped = {str(item.get("id")): item for item in events if item.get("id")}
    ordered = sorted(
        deduped.values(),
        key=lambda item: str(item.get("observed_at") or ""),
        reverse=True,
    )
    bounded = ordered[: max(1, min(limit, 5000))]
    counts: dict[str, int] = {}
    for item in bounded:
        category = str(item.get("category") or "system")
        counts[category] = counts.get(category, 0) + 1
    return {
        "count": len(bounded),
        "categories": counts,
        "events": bounded,
        "semantics": (
            "Timeline entries preserve upstream event provenance. Sentinel-derived reconnect, "
            "gap, energy, and incident entries state the evidence used for each derivation."
        ),
    }
