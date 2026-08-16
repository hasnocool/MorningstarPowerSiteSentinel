"""Historical continuity and controller energy reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from powersite_sentinel.config import Settings
from powersite_sentinel.models import Finding


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def forensic_period(days: int, *, now: datetime | None = None) -> tuple[str, str]:
    """Return a complete-day UTC window using inclusive-start/exclusive-end dates."""

    current = (now or datetime.now(UTC)).astimezone(UTC).date()
    return (current - timedelta(days=days)).isoformat(), current.isoformat()


def _controller_uid(controller: dict[str, object]) -> str:
    return str(controller.get("controller_uid") or controller.get("controller_id") or "")


def _duration_days(gap: dict[str, object]) -> int:
    value = gap.get("duration_days")
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _comparison_status(
    controller_wh: float | None,
    local_wh: float | None,
    difference_percent: float | None,
    integrated_seconds: float,
    settings: Settings,
) -> str:
    if controller_wh is None and local_wh is None:
        return "unavailable"
    if controller_wh is None:
        return "local_only"
    if local_wh is None:
        return "controller_only"
    if integrated_seconds < settings.energy_min_integrated_seconds:
        return "insufficient_local_coverage"
    if difference_percent is None:
        return "comparable"
    magnitude = abs(difference_percent)
    if magnitude >= settings.energy_discrepancy_critical_percent:
        return "strongly_divergent"
    if magnitude >= settings.energy_discrepancy_warning_percent:
        return "divergent"
    return "consistent"


def summarize_controller_history(
    controller: dict[str, object],
    bundle: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    """Normalize one controller's upstream history analytics without changing provenance."""

    uid = _controller_uid(controller)
    coverage = _dict(bundle.get("coverage"))
    gaps_payload = _dict(bundle.get("gaps"))
    energy_daily = _dict(bundle.get("energy_daily"))
    energy_summary = _dict(bundle.get("energy_summary"))

    gap_counts = {"recovered_days": 0, "partial_days": 0, "missing_days": 0}
    gaps: list[dict[str, object]] = []
    for raw in _list(gaps_payload.get("gaps")):
        if not isinstance(raw, dict):
            continue
        gap = dict(raw)
        gaps.append(gap)
        days = _duration_days(gap)
        status = str(gap.get("status") or "")
        if status == "recovered":
            gap_counts["recovered_days"] += days
        elif status == "partial":
            gap_counts["partial_days"] += days
        elif status == "missing":
            gap_counts["missing_days"] += days

    comparisons: list[dict[str, object]] = []
    for raw in _list(energy_daily.get("days")):
        if not isinstance(raw, dict):
            continue
        energy = _dict(raw.get("energy"))
        quality = _dict(raw.get("quality"))
        controller_wh = _number(energy.get("controller_reported_wh"))
        local_wh = _number(energy.get("integrated_output_wh"))
        difference_wh = _number(energy.get("difference_wh"))
        difference_percent = _number(energy.get("difference_percent"))
        integrated_seconds = _number(quality.get("integrated_seconds")) or 0.0
        comparisons.append(
            {
                "date": raw.get("date"),
                "controller_reported_wh": controller_wh,
                "integrated_output_wh": local_wh,
                "difference_wh": difference_wh,
                "difference_percent": difference_percent,
                "status": _comparison_status(
                    controller_wh,
                    local_wh,
                    difference_percent,
                    integrated_seconds,
                    settings,
                ),
                "quality": quality,
                "provenance": list(_list(quality.get("provenance"))),
            }
        )

    actionable = [
        item
        for item in comparisons
        if item["status"] in {"divergent", "strongly_divergent"}
    ]
    comparable = [
        item
        for item in comparisons
        if item["status"] in {"consistent", "divergent", "strongly_divergent", "comparable"}
    ]

    daily_evidence = _dict(coverage.get("daily_evidence"))
    realtime = _dict(coverage.get("realtime"))
    last_sync = _dict(_dict(coverage.get("reconciliation")).get("last_sync"))
    strongest = max(
        (
            abs(value)
            for item in actionable
            if (value := _number(item.get("difference_percent"))) is not None
        ),
        default=None,
    )

    return {
        "controller_uid": uid,
        "controller": controller,
        "period": coverage.get("period")
        or {"from": energy_daily.get("from"), "to": energy_daily.get("to")},
        "coverage": {
            "daily_evidence_percent": _number(daily_evidence.get("coverage_percent")),
            "realtime_day_percent": _number(realtime.get("coverage_percent")),
            "covered_days": daily_evidence.get("covered_days"),
            "days_with_samples": realtime.get("days_with_samples"),
            **gap_counts,
            "last_history_sync": last_sync or None,
        },
        "gaps": gaps,
        "energy": {
            "summary": energy_summary,
            "comparisons": comparisons,
            "comparable_days": len(comparable),
            "actionable_discrepancy_days": len(actionable),
            "largest_abs_difference_percent": strongest,
            "minimum_integrated_seconds_for_alert": settings.energy_min_integrated_seconds,
        },
        "provenance_policy": (
            "Controller-retained daily counters and locally integrated output-power samples "
            "remain separate evidence classes."
        ),
    }


def evaluate_forensic_findings(
    controller_reports: list[dict[str, object]],
    settings: Settings,
) -> list[Finding]:
    """Create persistent forensic findings only where historical evidence is sufficient."""

    findings: list[Finding] = []
    for report in controller_reports:
        uid = str(report.get("controller_uid") or "")
        if not uid:
            continue
        coverage = _dict(report.get("coverage"))
        missing_days = int(coverage.get("missing_days") or 0)
        partial_days = int(coverage.get("partial_days") or 0)
        if missing_days:
            severity = (
                "critical"
                if missing_days >= settings.history_missing_critical_days
                else "warning"
            )
            findings.append(
                Finding(
                    code="history_missing_days",
                    severity=severity,
                    title="Historical evidence has unrecovered gaps",
                    summary=(
                        f"{uid} has {missing_days} day(s) with neither persisted live samples "
                        "nor complete controller-retained daily evidence in the forensic window."
                    ),
                    evidence={
                        "controller_uid": uid,
                        "missing_days": missing_days,
                        "period": report.get("period"),
                    },
                )
            )
        if partial_days:
            findings.append(
                Finding(
                    code="history_partial_days",
                    severity="warning",
                    title="Historical gaps have only partial retained evidence",
                    summary=(
                        f"{uid} has {partial_days} day(s) without live samples where retained "
                        "controller evidence is incomplete."
                    ),
                    evidence={
                        "controller_uid": uid,
                        "partial_days": partial_days,
                        "period": report.get("period"),
                    },
                )
            )

        energy = _dict(report.get("energy"))
        comparisons = [
            item for item in _list(energy.get("comparisons")) if isinstance(item, dict)
        ]
        actionable = [
            item
            for item in comparisons
            if item.get("status") in {"divergent", "strongly_divergent"}
        ]
        if actionable:
            strongest = max(
                (
                    abs(value)
                    for item in actionable
                    if (value := _number(item.get("difference_percent"))) is not None
                ),
                default=0.0,
            )
            severity = (
                "critical"
                if strongest >= settings.energy_discrepancy_critical_percent
                else "warning"
            )
            findings.append(
                Finding(
                    code="energy_counter_discrepancy",
                    severity=severity,
                    title="Controller and locally integrated energy diverge",
                    summary=(
                        f"{uid} has {len(actionable)} comparable day(s) where controller-reported "
                        f"and locally integrated charging energy differ by up to {strongest:.1f}%."
                    ),
                    evidence={
                        "controller_uid": uid,
                        "actionable_days": [item.get("date") for item in actionable],
                        "largest_abs_difference_percent": round(strongest, 3),
                        "minimum_integrated_seconds": settings.energy_min_integrated_seconds,
                    },
                )
            )
    return findings


def observable_forensic_fingerprints(
    controller_reports: list[dict[str, object]],
) -> set[str]:
    """Return forensic incident fingerprints that current historical evidence can clear."""

    observable: set[str] = set()
    for report in controller_reports:
        uid = str(report.get("controller_uid") or "")
        if not uid:
            continue
        coverage = _dict(report.get("coverage"))
        if coverage.get("daily_evidence_percent") is not None:
            observable.add(f"history_missing_days:{uid}")
        if isinstance(report.get("gaps"), list):
            observable.add(f"history_partial_days:{uid}")

        comparisons = [
            item
            for item in _list(_dict(report.get("energy")).get("comparisons"))
            if isinstance(item, dict)
        ]
        if any(
            item.get("status")
            in {"consistent", "divergent", "strongly_divergent", "comparable"}
            for item in comparisons
        ):
            observable.add(f"energy_counter_discrepancy:{uid}")
    return observable


def site_forensic_summary(controller_reports: list[dict[str, object]]) -> dict[str, object]:
    """Aggregate compact forensic counts without summing incompatible energy sources."""

    missing_days = 0
    partial_days = 0
    recovered_days = 0
    discrepancy_days = 0
    daily_coverages: list[float] = []
    for report in controller_reports:
        coverage = _dict(report.get("coverage"))
        missing_days += int(coverage.get("missing_days") or 0)
        partial_days += int(coverage.get("partial_days") or 0)
        recovered_days += int(coverage.get("recovered_days") or 0)
        if (value := _number(coverage.get("daily_evidence_percent"))) is not None:
            daily_coverages.append(value)
        discrepancy_days += int(
            _dict(report.get("energy")).get("actionable_discrepancy_days") or 0
        )
    return {
        "controller_count": len(controller_reports),
        "missing_controller_days": missing_days,
        "partial_controller_days": partial_days,
        "recovered_controller_days": recovered_days,
        "energy_discrepancy_controller_days": discrepancy_days,
        "minimum_daily_evidence_percent": min(daily_coverages) if daily_coverages else None,
        "average_daily_evidence_percent": (
            round(sum(daily_coverages) / len(daily_coverages), 2)
            if daily_coverages
            else None
        ),
    }
