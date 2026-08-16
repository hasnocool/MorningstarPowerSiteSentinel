import asyncio

from powersite_sentinel.incidents import IncidentStore
from powersite_sentinel.models import Finding


def test_incident_lifecycle(tmp_path) -> None:
    async def scenario() -> None:
        store = IncidentStore(str(tmp_path / "sentinel.db"))
        finding = Finding("controller_offline", "warning", "Offline", "One controller offline")
        first = await store.reconcile("sys_default", [finding])
        assert len(first) == 1
        assert first[0]["occurrences"] == 1

        second = await store.reconcile("sys_default", [finding])
        assert len(second) == 1
        assert second[0]["occurrences"] == 2

        open_after_clear = await store.reconcile("sys_default", [])
        assert open_after_clear == []
        resolved = await store.list(site_uid="sys_default", status="resolved")
        assert len(resolved) == 1
        assert resolved[0]["resolved_at"] is not None

    asyncio.run(scenario())
