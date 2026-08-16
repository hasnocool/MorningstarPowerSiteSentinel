from datetime import UTC, datetime, timedelta

from powersite_sentinel.config import Settings
from powersite_sentinel.rules import evaluate_findings, observable_incident_fingerprints


def test_conflict_residual_and_soc_findings() -> None:
    now = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
    snapshot = {
        "controllers": [{"controller_uid": "ctrl_a", "status": "online"}],
        "latest": {"observed_at": now.isoformat()},
        "power_flow": {
            "observed_at": now.isoformat(),
            "quality": "partial",
            "battery": {
                "soc_percent": {"value": 12.0, "quality": "complete"},
                "net_current_a": {
                    "value": None,
                    "quality": "conflict",
                    "resolution": "conflict",
                    "reason": "Two system reporters disagree.",
                },
            },
            "balance": {
                "system_charge_power_w": {"value": 400.0},
                "whole_system_residual_w": {"value": 100.0},
            },
        },
    }
    codes = {item.code: item for item in evaluate_findings(snapshot, Settings(), now=now)}
    assert codes["measurement_conflict"].severity == "warning"
    assert codes["power_balance_residual"].severity == "critical"
    assert codes["reported_soc_low"].severity == "critical"


def test_stale_and_offline_site_is_critical() -> None:
    now = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
    old = now - timedelta(minutes=10)
    snapshot = {
        "controllers": [{"controller_uid": "ctrl_a", "status": "offline"}],
        "latest": {"observed_at": old.isoformat()},
        "power_flow": {"observed_at": old.isoformat(), "quality": "empty"},
    }
    findings = evaluate_findings(snapshot, Settings(stale_after_seconds=30), now=now)
    by_code = {item.code: item for item in findings}
    assert by_code["telemetry_stale"].severity == "critical"
    assert by_code["controller_offline"].severity == "critical"


def test_controller_alarm_and_fault_metrics_create_findings() -> None:
    now = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
    snapshot = {
        "controllers": [{"controller_uid": "ctrl_a", "status": "online"}],
        "latest": {
            "observed_at": now.isoformat(),
            "metrics": {
                "faults": {
                    "value": ["battery_high_voltage_disconnect"],
                    "quality": "complete",
                    "contributors": 1,
                    "expected_contributors": 1,
                },
                "alarms": {
                    "value": ["rts_open"],
                    "quality": "complete",
                    "contributors": 1,
                    "expected_contributors": 1,
                },
            },
        },
        "power_flow": {"observed_at": now.isoformat(), "quality": "partial"},
    }

    findings = {item.code: item for item in evaluate_findings(snapshot, Settings(), now=now)}

    assert findings["controller_fault_active"].severity == "critical"
    assert findings["controller_alarm_active"].severity == "warning"
    assert "rts open" in findings["controller_alarm_active"].summary
    observable = observable_incident_fingerprints(snapshot)
    assert "controller_fault_active:latest.metrics.faults" in observable
    assert "controller_alarm_active:latest.metrics.alarms" in observable


def test_controller_alarm_is_warning_and_clear_fault_does_not_fire() -> None:
    now = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
    snapshot = {
        "controllers": [{"controller_uid": "ctrl_a", "status": "online"}],
        "latest": {
            "observed_at": now.isoformat(),
            "metrics": {
                "faults": {
                    "value": ["NONE"],
                    "quality": "complete",
                    "contributors": 1,
                    "expected_contributors": 1,
                },
                "alarms": {
                    "value": ["rts_open"],
                    "quality": "complete",
                    "contributors": 1,
                    "expected_contributors": 1,
                },
            },
        },
        "power_flow": {"observed_at": now.isoformat(), "quality": "partial"},
    }

    findings = evaluate_findings(snapshot, Settings(), now=now)
    by_code = {item.code: item for item in findings}
    assert by_code["controller_alarm_active"].severity == "warning"
    assert "rts open" in by_code["controller_alarm_active"].summary
    assert "controller_fault_active" not in by_code

    observable = observable_incident_fingerprints(snapshot)
    assert "controller_alarm_active:latest.metrics.alarms" in observable
    assert "controller_fault_active:latest.metrics.faults" in observable


def test_clear_controller_faults_and_alarms_do_not_create_findings() -> None:
    now = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
    snapshot = {
        "controllers": [{"controller_uid": "ctrl_a", "status": "online"}],
        "latest": {
            "observed_at": now.isoformat(),
            "metrics": {
                "faults": {"value": ["NONE"], "quality": "complete", "contributors": 1},
                "alarms": {"value": [], "quality": "complete", "contributors": 1},
            },
        },
        "power_flow": {"observed_at": now.isoformat(), "quality": "partial"},
    }

    codes = {item.code for item in evaluate_findings(snapshot, Settings(), now=now)}
    assert "controller_fault_active" not in codes
    assert "controller_alarm_active" not in codes


def test_only_currently_observable_signals_can_resolve_incidents() -> None:
    snapshot = {
        "controllers": [{"controller_uid": "ctrl_a", "status": "online"}],
        "latest": {"observed_at": "2026-08-16T04:00:00+00:00"},
        "power_flow": {
            "observed_at": "2026-08-16T04:00:00+00:00",
            "battery": {
                "soc_percent": {"value": None, "quality": "empty", "status": "unknown"},
                "net_current_a": {"value": None, "quality": "empty", "status": "unknown"},
            },
            "balance": {
                "whole_system_residual_w": {
                    "value": None,
                    "quality": "empty",
                    "status": "unknown",
                },
            },
        },
    }
    observable = observable_incident_fingerprints(snapshot)
    assert "telemetry_stale:site" in observable
    assert "controller_offline:site" in observable
    assert "controller_degraded:site" in observable
    assert "reported_soc_low:site" not in observable
    assert "power_balance_residual:power_flow.balance.whole_system_residual_w" not in observable
    assert "measurement_conflict:battery.net_current_a" not in observable
    assert "controller_fault_active:latest.metrics.faults" not in observable
    assert "controller_alarm_active:latest.metrics.alarms" not in observable
