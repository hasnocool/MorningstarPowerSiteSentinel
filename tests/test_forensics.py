from powersite_sentinel.config import Settings
from powersite_sentinel.forensics import (
    evaluate_forensic_findings,
    observable_forensic_fingerprints,
    site_forensic_summary,
    summarize_controller_history,
)


def _bundle() -> dict[str, object]:
    return {
        "coverage": {
            "period": {"from": "2026-08-10", "to": "2026-08-15", "day_count": 5},
            "realtime": {"coverage_percent": 40.0, "days_with_samples": 2},
            "daily_evidence": {
                "coverage_percent": 80.0,
                "covered_days": 4,
                "recovered_days": 2,
                "missing_days": 1,
            },
            "reconciliation": {"last_sync": {"status": "ok"}},
        },
        "gaps": {
            "gaps": [
                {"from": "2026-08-11", "to": "2026-08-13", "duration_days": 2, "status": "recovered"},
                {"from": "2026-08-14", "to": "2026-08-15", "duration_days": 1, "status": "missing"},
            ]
        },
        "energy_daily": {
            "days": [
                {
                    "date": "2026-08-10",
                    "energy": {
                        "controller_reported_wh": 1000.0,
                        "integrated_output_wh": 700.0,
                        "difference_wh": -300.0,
                        "difference_percent": -30.0,
                    },
                    "quality": {
                        "integrated_seconds": 7200.0,
                        "provenance": ["live_poll", "controller_internal_logger"],
                    },
                },
                {
                    "date": "2026-08-11",
                    "energy": {
                        "controller_reported_wh": 1000.0,
                        "integrated_output_wh": 100.0,
                        "difference_wh": -900.0,
                        "difference_percent": -90.0,
                    },
                    "quality": {
                        "integrated_seconds": 300.0,
                        "provenance": ["live_poll", "controller_internal_logger"],
                    },
                },
            ]
        },
        "energy_summary": {"energy": {}},
    }


def test_controller_forensics_requires_sufficient_local_energy_coverage() -> None:
    settings = Settings(
        energy_min_integrated_seconds=3600.0,
        energy_discrepancy_warning_percent=10.0,
        energy_discrepancy_critical_percent=25.0,
    )
    report = summarize_controller_history(
        {"controller_uid": "ctrl_a", "status": "online"}, _bundle(), settings
    )
    comparisons = report["energy"]["comparisons"]
    assert comparisons[0]["status"] == "strongly_divergent"
    assert comparisons[1]["status"] == "insufficient_local_coverage"
    assert report["energy"]["actionable_discrepancy_days"] == 1
    findings = evaluate_forensic_findings([report], settings)
    by_code = {finding.code: finding for finding in findings}
    assert by_code["history_missing_days"].severity == "warning"
    assert by_code["energy_counter_discrepancy"].severity == "critical"
    observable = observable_forensic_fingerprints([report])
    assert "history_missing_days:ctrl_a" in observable
    assert "energy_counter_discrepancy:ctrl_a" in observable


def test_site_forensic_summary_never_sums_energy_measurements() -> None:
    report = summarize_controller_history(
        {"controller_uid": "ctrl_a"}, _bundle(), Settings(energy_min_integrated_seconds=3600.0)
    )
    summary = site_forensic_summary([report])
    assert summary["missing_controller_days"] == 1
    assert summary["recovered_controller_days"] == 2
    assert summary["energy_discrepancy_controller_days"] == 1
    assert "energy_wh" not in summary
