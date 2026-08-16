from datetime import UTC, datetime, timedelta

from powersite_sentinel.config import Settings
from powersite_sentinel.rules import evaluate_findings


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
