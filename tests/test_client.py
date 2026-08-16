import asyncio

import httpx

from powersite_sentinel.client import MorningstarApiClient


def test_site_snapshot_reads_system_surfaces() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        is_list = request.url.path.endswith("/controllers") or request.url.path.endswith("/events")
        payload: object = [] if is_list else {}
        if request.url.path == "/v1/systems/sys_default":
            payload = {"system_uid": "sys_default"}
        return httpx.Response(200, json=payload)

    async def scenario() -> None:
        client = MorningstarApiClient("http://test", transport=httpx.MockTransport(handler))
        snapshot = await client.site_snapshot("sys_default")
        assert snapshot["site"] == {"system_uid": "sys_default"}
        assert "/v1/systems/sys_default/power-flow" in seen
        assert "/v1/systems/sys_default/energy-ledger" in seen
        assert "/v1/systems/sys_default/component-graph" in seen

    asyncio.run(scenario())


def test_connection_failures_are_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("upstream is still starting", request=request)
        return httpx.Response(
            200,
            json=[{"system_uid": "sys_default", "name": "default"}],
        )

    async def scenario() -> None:
        client = MorningstarApiClient(
            "http://test",
            connect_attempts=3,
            retry_backoff_seconds=0.0,
            transport=httpx.MockTransport(handler),
        )
        sites = await client.list_sites()
        assert sites == [{"system_uid": "sys_default", "name": "default"}]

    asyncio.run(scenario())
    assert attempts == 3
