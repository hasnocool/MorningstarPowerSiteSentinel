"""Health and observability scoring with explicit explanations."""

from __future__ import annotations

import datetime as dt

from powersite_sentinel.config import Settings
from powersite_sentinel.models import Finding, Score

_CONTROLLER_TELEMETRY_METRICS = (
    "solar_input_power_w",
    "charge_output_power_w",
    "battery_charge_current_a",
    "battery_voltage_v",
    "array_voltage_v",
    "daily_charge_wh",
    "daily_charge_kwh",
    "charge_state",
    "faults",
    "alarms",
)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _metric_known(payload: object) -> bool:
    return isinstance(payload, dict) and _number(payload.get("value")) is not None


def _status(value: int) -> str:
    if value >= 85:
        return "healthy"
    if value >= 60:
        return "attention"
    return "critical"


def _controller_telemetry_coverage(snapshot: dict[str, object]) -> tuple[int, int, int] | None:
    """Return capability-aware coverage for controller-native normalized metrics."""
    latest = snapshot.get("latest") if isinstance(snapshot.get("latest"), dict) else {}
    metrics = latest.get("metrics") if isinstance(latest.get("metrics"), dict) else {}

    supported = 0
    reporting = 0
    for name in _CONTROLLER_TELEMETRY_METRICS:
        payload = metrics.get(name)
        if not isinstance(payload, dict):
            continue
        expected = _number(payload.get("expected_contributors"))
        if expected is None or expected <= 0:
            continue
        supported += 1
        contributors = _number(payload.get("contributors")) or 0.0
        if contributors >= expected:
            reporting += 1

    if supported == 0:
        return None
    return round(reporting / supported * 100), reporting, supported


def calculate_scores(
    snapshot: dict[str, object],
    findings: list[Finding],
    settings: Settings,
    *,
    now: dt.datetime | None = None,
) -> dict[str, object]:
    controllers = snapshot.get("controllers") if isinstance(snapshot.get("controllers"), list) else []
    current = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)

    communication = 100
    offline = 0
    degraded = 0
    for item in controllers:
        if not isinstance(item, dict):
            continue
        state = str(item.get("status") or "").lower()
        if state in {"offline", "missing", "unavailable"}:
            offline += 1
        elif state in {"degraded", "error", "stale"}:
            degraded += 1
    if controllers:
        communication -= round(80 * offline / len(controllers))
        communication -= round(30 * degraded / len(controllers))
    communication = max(0, communication)

    freshness = 100
    stale_finding = next((item for item in findings if item.code == "telemetry_stale"), None)
    if stale_finding:
        age = _number(stale_finding.evidence.get("age_seconds")) or settings.stale_after_seconds
        ratio = age / max(settings.stale_after_seconds, 1.0)
        freshness = max(0, round(100 - min(100, (ratio - 1.0) * 25)))

    operational = 100
    for finding in findings:
        if finding.severity == "critical":
            operational -= 35
        elif finding.severity == "warning":
            operational -= 12
    operational = max(0, operational)

    power_flow = snapshot.get("power_flow") if isinstance(snapshot.get("power_flow"), dict) else {}
    battery = power_flow.get("battery") if isinstance(power_flow.get("battery"), dict) else {}
    loads = power_flow.get("loads") if isinstance(power_flow.get("loads"), dict) else {}
    sources = power_flow.get("sources") if isinstance(power_flow.get("sources"), dict) else {}
    balance = power_flow.get("balance") if isinstance(power_flow.get("balance"), dict) else {}

    accounting_checks = (
        _metric_known(sources.get("solar_input_power_w")),
        _metric_known(battery.get("net_power_w")),
        _metric_known(loads.get("dc_power_w")),
        _metric_known(balance.get("system_charge_power_w")),
        _metric_known(battery.get("soc_percent")),
    )
    power_accounting = round(
        sum(1 for item in accounting_checks if item) / len(accounting_checks) * 100
    )

    telemetry_coverage = _controller_telemetry_coverage(snapshot)
    if telemetry_coverage is None:
        observability = power_accounting
        observed_metrics = sum(1 for item in accounting_checks if item)
        supported_metrics = len(accounting_checks)
    else:
        observability, observed_metrics, supported_metrics = telemetry_coverage

    overall = round(communication * 0.35 + freshness * 0.25 + operational * 0.40)
    dimensions = [
        Score(
            "communications",
            communication,
            _status(communication),
            f"{offline} offline and {degraded} degraded controller(s) out of {len(controllers)}.",
        ),
        Score(
            "freshness",
            freshness,
            _status(freshness),
            (
                f"Evaluated at {current.isoformat()} against a "
                f"{settings.stale_after_seconds:.0f}s stale threshold."
            ),
        ),
        Score(
            "operations",
            operational,
            _status(operational),
            "Penalty is based only on current evidence-backed warning/critical findings.",
        ),
    ]
    return {
        "overall": {
            "value": overall,
            "status": _status(overall),
            "explanation": (
                "Weighted communications, freshness, and evidence-backed operational findings. "
                "A high score means no problem was detected in observed evidence; it does not imply "
                "that every whole-site electrical quantity is measured."
            ),
        },
        "observability": {
            "value": observability,
            "status": "high" if observability >= 80 else "partial" if observability >= 40 else "limited",
            "observed_metrics": observed_metrics,
            "supported_metrics": supported_metrics,
            "explanation": (
                "Capability-aware coverage of controller-native telemetry expected from the "
                "enrolled hardware."
            ),
        },
        "power_accounting": {
            "value": power_accounting,
            "status": (
                "complete"
                if power_accounting >= 80
                else "partial"
                if power_accounting >= 40
                else "limited"
            ),
            "explanation": (
                "Whole-site electrical accounting completeness. Battery net flow, load power, and SOC "
                "remain unmeasured unless source-backed system/shunt sensors provide them."
            ),
        },
        "dimensions": [item.to_dict() for item in dimensions],
    }
