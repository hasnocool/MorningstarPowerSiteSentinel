"""Deterministic, evidence-preserving Sentinel anomaly rules."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from powersite_sentinel.config import Settings
from powersite_sentinel.models import Finding


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _walk(value: object, path: str = "") -> Iterator[tuple[str, dict[str, object]]]:
    if isinstance(value, dict):
        payload = {str(key): item for key, item in value.items()}
        yield path or "$", payload
        for key, item in payload.items():
            child = f"{path}.{key}" if path else key
            yield from _walk(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


def observable_incident_fingerprints(snapshot: dict[str, object]) -> set[str]:
    """Return incident fingerprints that current evidence can safely resolve.

    Absence of a measurement is not evidence that an earlier condition cleared.
    A fingerprint is included only when the underlying signal is currently present.
    """

    observable: set[str] = set()
    power_flow = snapshot.get("power_flow") if isinstance(snapshot.get("power_flow"), dict) else {}
    latest = snapshot.get("latest") if isinstance(snapshot.get("latest"), dict) else {}
    controllers = snapshot.get("controllers") if isinstance(snapshot.get("controllers"), list) else []

    if _parse_time(power_flow.get("observed_at") or latest.get("observed_at")) is not None:
        observable.add("telemetry_stale:site")

    if controllers:
        observable.add("controller_offline:site")
        observable.add("controller_degraded:site")

    for path, payload in _walk(power_flow):
        quality = str(payload.get("quality") or "")
        status = str(payload.get("status") or "")
        has_value = _number(payload.get("value")) is not None
        has_positive_evidence = has_value or quality in {"complete", "partial", "derived"}
        has_positive_evidence = has_positive_evidence or status in {"observed", "derived"}
        if has_positive_evidence:
            observable.add(f"measurement_conflict:{path}")

    balance = power_flow.get("balance") if isinstance(power_flow.get("balance"), dict) else {}
    residual_payload = (
        balance.get("whole_system_residual_w")
        if isinstance(balance.get("whole_system_residual_w"), dict)
        else {}
    )
    if _number(residual_payload.get("value")) is not None:
        observable.add("power_balance_residual:power_flow.balance.whole_system_residual_w")

    battery = power_flow.get("battery") if isinstance(power_flow.get("battery"), dict) else {}
    soc_payload = battery.get("soc_percent") if isinstance(battery.get("soc_percent"), dict) else {}
    if _number(soc_payload.get("value")) is not None:
        observable.add("reported_soc_low:site")

    return observable


def evaluate_findings(
    snapshot: dict[str, object],
    settings: Settings,
    *,
    now: datetime | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    current = (now or datetime.now(UTC)).astimezone(UTC)
    power_flow = snapshot.get("power_flow") if isinstance(snapshot.get("power_flow"), dict) else {}
    latest = snapshot.get("latest") if isinstance(snapshot.get("latest"), dict) else {}
    controllers = snapshot.get("controllers") if isinstance(snapshot.get("controllers"), list) else []

    observed_at = _parse_time(power_flow.get("observed_at") or latest.get("observed_at"))
    if observed_at is not None:
        age = max(0.0, (current - observed_at).total_seconds())
        if age > settings.stale_after_seconds:
            severity = "critical" if age > settings.stale_after_seconds * 5 else "warning"
            findings.append(
                Finding(
                    code="telemetry_stale",
                    severity=severity,
                    title="Site telemetry is stale",
                    summary=f"The newest system observation is {age:.0f} seconds old.",
                    evidence={"age_seconds": round(age, 3), "observed_at": observed_at.isoformat()},
                )
            )

    offline: list[str] = []
    degraded: list[str] = []
    for item in controllers:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").lower()
        uid = str(item.get("controller_uid") or item.get("controller_id") or "unknown")
        if status in {"offline", "missing", "unavailable"}:
            offline.append(uid)
        elif status in {"degraded", "error", "stale"}:
            degraded.append(uid)
    if offline:
        severity = "critical" if len(offline) == len(controllers) and controllers else "warning"
        findings.append(
            Finding(
                code="controller_offline",
                severity=severity,
                title="Controller communication is unavailable",
                summary=f"{len(offline)} controller(s) are reported offline.",
                evidence={"controller_uids": offline},
            )
        )
    if degraded:
        findings.append(
            Finding(
                code="controller_degraded",
                severity="warning",
                title="Controller communication is degraded",
                summary=f"{len(degraded)} controller(s) are reported degraded or stale.",
                evidence={"controller_uids": degraded},
            )
        )

    seen_conflicts: set[str] = set()
    for path, payload in _walk(power_flow):
        if payload.get("quality") != "conflict" or path in seen_conflicts:
            continue
        seen_conflicts.add(path)
        findings.append(
            Finding(
                code="measurement_conflict",
                severity="warning",
                title="Independent measurements disagree",
                summary=str(payload.get("reason") or f"Conflicting system observations at {path}."),
                evidence={"path": path, "resolution": payload.get("resolution")},
            )
        )

    balance = power_flow.get("balance") if isinstance(power_flow.get("balance"), dict) else {}
    residual_payload = (
        balance.get("whole_system_residual_w")
        if isinstance(balance.get("whole_system_residual_w"), dict)
        else {}
    )
    charge_payload = (
        balance.get("system_charge_power_w")
        if isinstance(balance.get("system_charge_power_w"), dict)
        else {}
    )
    residual = _number(residual_payload.get("value"))
    charge = _number(charge_payload.get("value"))
    if residual is not None:
        reference = max(abs(charge or 0.0), 1.0)
        percent = abs(residual) / reference * 100.0
        if abs(residual) >= settings.residual_warning_w and percent >= settings.residual_warning_percent:
            severity = "critical" if percent >= settings.residual_critical_percent else "warning"
            findings.append(
                Finding(
                    code="power_balance_residual",
                    severity=severity,
                    title="Power balance does not close",
                    summary=(
                        f"The source-backed DC balance leaves {residual:+.1f} W unaccounted "
                        f"({percent:.1f}% of system charge power)."
                    ),
                    evidence={
                        "residual_w": residual,
                        "reference_charge_w": charge,
                        "percent": round(percent, 3),
                        "path": "power_flow.balance.whole_system_residual_w",
                    },
                )
            )

    battery = power_flow.get("battery") if isinstance(power_flow.get("battery"), dict) else {}
    soc_payload = battery.get("soc_percent") if isinstance(battery.get("soc_percent"), dict) else {}
    soc = _number(soc_payload.get("value"))
    if soc is not None and soc <= settings.soc_warning_percent:
        severity = "critical" if soc <= settings.soc_critical_percent else "warning"
        findings.append(
            Finding(
                code="reported_soc_low",
                severity=severity,
                title="Reported battery state of charge is low",
                summary=(
                    f"The authoritative upstream telemetry reports {soc:.1f}% SOC, below the "
                    f"configured {settings.soc_warning_percent:.1f}% warning threshold."
                ),
                evidence={"soc_percent": soc, "source_quality": soc_payload.get("quality")},
            )
        )

    if power_flow.get("quality") == "empty":
        findings.append(
            Finding(
                code="power_visibility_empty",
                severity="info",
                title="Power-flow visibility is limited",
                summary="The upstream API has no current source-backed system power measurements.",
                evidence={"unknowns": power_flow.get("unknowns", [])},
            )
        )
    return findings
