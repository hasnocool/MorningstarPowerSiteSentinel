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


def test_controller_snapshot_reads_rich_surfaces_on_demand() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/v1/controllers/controller_a":
            return httpx.Response(
                200,
                json={"controller_uid": "controller_a", "model": "TS-MPPT-60"},
            )
        if request.url.path.endswith("/latest"):
            return httpx.Response(200, json={"values": [{"register_name": "battery_voltage"}]})
        return httpx.Response(200, json={})

    async def scenario() -> None:
        client = MorningstarApiClient("http://test", transport=httpx.MockTransport(handler))
        snapshot = await client.controller_snapshot("controller_a")
        assert snapshot["controller"] == {
            "controller_uid": "controller_a",
            "model": "TS-MPPT-60",
        }
        assert "/v1/controllers/controller_a/latest" in seen
        assert "/v1/controllers/controller_a/history/summary" in seen
        assert "/v1/controllers/controller_a/history/controller-daily/summary" in seen
        assert "/v1/controllers/controller_a/history/coverage" in seen
        assert "/v1/controllers/controller_a/polling/performance" in seen

    asyncio.run(scenario())


def test_controller_snapshot_tolerates_optional_surface_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/controllers/controller_a":
            return httpx.Response(200, json={"controller_uid": "controller_a"})
        if request.url.path.endswith("/latest"):
            return httpx.Response(404, json={"detail": "no samples for controller"})
        return httpx.Response(200, json={})

    async def scenario() -> None:
        client = MorningstarApiClient("http://test", transport=httpx.MockTransport(handler))
        snapshot = await client.controller_snapshot("controller_a")
        assert snapshot["controller"] == {"controller_uid": "controller_a"}
        assert snapshot["latest"]["status"] == "unavailable"

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
