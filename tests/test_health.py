from datetime import UTC, datetime

from powersite_sentinel.config import Settings
from powersite_sentinel.health import calculate_scores
from powersite_sentinel.models import Finding


def test_observability_is_separate_from_health() -> None:
    snapshot = {
        "controllers": [{"controller_uid": "ctrl_a", "status": "online"}],
        "power_flow": {
            "sources": {"solar_input_power_w": {"value": 500.0}},
            "battery": {"net_power_w": {"value": None}, "soc_percent": {"value": None}},
            "loads": {"dc_power_w": {"value": None}},
            "balance": {"system_charge_power_w": {"value": 470.0}},
        },
    }
    scores = calculate_scores(
        snapshot,
        [],
        Settings(),
        now=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
    )
    assert scores["overall"]["value"] == 100
    assert scores["observability"]["value"] == 40


def test_warnings_reduce_operational_health() -> None:
    finding = Finding("x", "warning", "Warning", "Evidence-backed warning")
    scores = calculate_scores(
        {"controllers": [{"controller_uid": "a", "status": "online"}], "power_flow": {}},
        [finding],
        Settings(),
        now=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
    )
    operational = next(item for item in scores["dimensions"] if item["name"] == "operations")
    assert operational["value"] == 88
