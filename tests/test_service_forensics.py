import asyncio

from powersite_sentinel.config import Settings
from powersite_sentinel.incidents import IncidentStore
from powersite_sentinel.service import SentinelService


class FakeForensicClient:
    def __init__(self) -> None:
        self.calls = 0

    async def site_forensic_snapshot(
        self,
        site_uid: str,
        *,
        start: str,
        end: str,
        max_gap_seconds: int,
        event_limit: int,
    ) -> dict[str, object]:
        self.calls += 1
        return {
            "site_uid": site_uid,
            "controllers": [{"controller_uid": "ctrl_a", "status": "online"}],
            "events": [
                {
                    "id": "fault-1",
                    "controller_uid": "ctrl_a",
                    "observed_at": f"{start}T12:00:00+00:00",
                    "event_type": "FAULT_STARTED",
                    "severity": "critical",
                    "source": "live-modbus",
                    "message": "",
                    "payload": {"value": 1},
                }
            ],
            "history": {
                "ctrl_a": {
                    "coverage": {
                        "period": {"from": start, "to": end, "day_count": 2},
                        "realtime": {"coverage_percent": 50.0, "days_with_samples": 1},
                        "daily_evidence": {
                            "coverage_percent": 50.0,
                            "covered_days": 1,
                            "recovered_days": 0,
                            "missing_days": 1,
                        },
                        "reconciliation": {"last_sync": {"status": "ok"}},
                    },
                    "gaps": {
                        "gaps": [
                            {
                                "from": start,
                                "to": end,
                                "duration_days": 1,
                                "status": "missing",
                            }
                        ]
                    },
                    "energy_daily": {"days": []},
                    "energy_summary": {"energy": {}},
                }
            },
        }


def test_forensic_report_persists_findings_and_uses_cache(tmp_path) -> None:
    async def scenario() -> None:
        client = FakeForensicClient()
        service = SentinelService(
            client,  # type: ignore[arg-type]
            IncidentStore(str(tmp_path / "sentinel.db")),
            Settings(forensic_cache_seconds=3600.0),
        )
        first = await service.forensic_report("sys_default", days=2, event_limit=100)
        assert first["summary"]["missing_controller_days"] == 1
        assert first["open_incidents"][0]["code"] == "history_missing_days"
        assert any(
            event["event_type"] == "HISTORY_GAP_MISSING"
            for event in first["timeline"]["events"]
        )
        second = await service.forensic_report("sys_default", days=2, event_limit=100)
        assert second["generated_at"] == first["generated_at"]
        assert client.calls == 1

    asyncio.run(scenario())
