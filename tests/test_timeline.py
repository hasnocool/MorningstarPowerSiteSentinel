from powersite_sentinel.timeline import build_unified_timeline


def test_timeline_merges_events_reconnects_gaps_energy_and_incidents() -> None:
    upstream = [
        {
            "id": "err-1",
            "controller_uid": "ctrl_a",
            "observed_at": "2026-08-12T10:00:00+00:00",
            "event_type": "COMMUNICATION_ERROR",
            "severity": "warning",
            "source": "modbus-poll",
            "message": "timeout",
            "payload": {},
        },
        {
            "id": "charge-1",
            "controller_uid": "ctrl_a",
            "observed_at": "2026-08-12T10:05:00+00:00",
            "event_type": "ABSORPTION_ENTERED",
            "severity": "info",
            "source": "live-modbus",
            "message": "",
            "payload": {"previous": "MPPT", "value": "Absorption"},
        },
        {
            "id": "alarm-1",
            "controller_uid": "ctrl_a",
            "observed_at": "2026-08-12T10:06:00+00:00",
            "event_type": "ALARM_STARTED",
            "severity": "warning",
            "source": "live-modbus",
            "message": "",
            "payload": {"value": 1},
        },
    ]
    controller_reports = [
        {
            "controller_uid": "ctrl_a",
            "gaps": [
                {
                    "from": "2026-08-10",
                    "to": "2026-08-11",
                    "duration_days": 1,
                    "status": "recovered",
                }
            ],
            "energy": {
                "comparisons": [
                    {
                        "date": "2026-08-11",
                        "controller_reported_wh": 2000.0,
                        "integrated_output_wh": 1500.0,
                        "difference_percent": -25.0,
                        "status": "divergent",
                    }
                ]
            },
        }
    ]
    incidents = [
        {
            "incident_id": "inc_1",
            "fingerprint": "history_missing_days:ctrl_a",
            "code": "history_missing_days",
            "severity": "warning",
            "title": "Historical gap",
            "summary": "Missing evidence",
            "status": "resolved",
            "first_seen": "2026-08-13T00:00:00+00:00",
            "resolved_at": "2026-08-14T00:00:00+00:00",
            "evidence": {"controller_uid": "ctrl_a"},
        }
    ]
    result = build_unified_timeline(
        "sys_default",
        upstream,
        [{"controller_uid": "ctrl_a", "status": "online"}],
        controller_reports,
        incidents,
        limit=100,
    )
    event_types = {item["event_type"] for item in result["events"]}
    assert "COMMUNICATION_ERROR" in event_types
    assert "COMMUNICATION_RECOVERED" in event_types
    assert "ABSORPTION_ENTERED" in event_types
    assert "ALARM_STARTED" in event_types
    assert "HISTORY_GAP_RECOVERED" in event_types
    assert "ENERGY_COUNTER_DISCREPANCY" in event_types
    assert "SENTINEL_INCIDENT_OPENED" in event_types
    assert "SENTINEL_INCIDENT_RESOLVED" in event_types

    reconnect = next(
        item for item in result["events"] if item["event_type"] == "COMMUNICATION_RECOVERED"
    )
    assert reconnect["source"] == "sentinel-derived"
    assert reconnect["provenance"] == ["communication_error", "later_live_observation"]
