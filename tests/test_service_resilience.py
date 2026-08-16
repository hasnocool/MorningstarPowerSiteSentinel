import asyncio

from powersite_sentinel.client import MorningstarApiError
from powersite_sentinel.config import Settings
from powersite_sentinel.service import SentinelService


class FlakyClient:
    def __init__(self) -> None:
        self.calls = 0

    async def list_sites(self):
        self.calls += 1
        if self.calls == 1:
            return [{"system_uid": "sys_default", "name": "default"}]
        raise MorningstarApiError("upstream unavailable")


class DummyStore:
    pass


def test_list_sites_uses_last_known_good_inventory_during_outage() -> None:
    async def scenario() -> None:
        client = FlakyClient()
        service = SentinelService(client, DummyStore(), Settings(monitor_enabled=False))  # type: ignore[arg-type]

        first = await service.list_sites()
        second = await service.list_sites()

        assert first == [{"system_uid": "sys_default", "name": "default"}]
        assert second == first
        assert second is not first

    asyncio.run(scenario())
