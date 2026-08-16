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


def test_site_forensic_snapshot_reads_controller_history_analytics() -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params)))
        if request.url.path == "/v1/systems/sys_default/controllers":
            return httpx.Response(
                200,
                json=[{"controller_uid": "ctrl_a", "status": "online"}],
            )
        if request.url.path == "/v1/systems/sys_default/events":
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/history/coverage"):
            return httpx.Response(200, json={"daily_evidence": {"coverage_percent": 100.0}})
        if request.url.path.endswith("/history/gaps"):
            return httpx.Response(200, json={"gaps": []})
        if request.url.path.endswith("/energy/daily"):
            return httpx.Response(200, json={"days": []})
        if request.url.path.endswith("/energy/summary"):
            return httpx.Response(200, json={"energy": {}})
        return httpx.Response(404)

    async def scenario() -> None:
        client = MorningstarApiClient("http://test", transport=httpx.MockTransport(handler))
        snapshot = await client.site_forensic_snapshot(
            "sys_default",
            start="2026-08-01",
            end="2026-08-15",
            max_gap_seconds=300,
            event_limit=1000,
        )
        assert snapshot["history"]["ctrl_a"]["coverage"]["daily_evidence"]["coverage_percent"] == 100.0
        paths = {path for path, _params in seen}
        assert "/v1/controllers/ctrl_a/history/coverage" in paths
        assert "/v1/controllers/ctrl_a/history/gaps" in paths
        assert "/v1/controllers/ctrl_a/energy/daily" in paths
        assert "/v1/controllers/ctrl_a/energy/summary" in paths

        energy_daily = next(
            params for path, params in seen if path == "/v1/controllers/ctrl_a/energy/daily"
        )
        assert energy_daily["from"] == "2026-08-01"
        assert energy_daily["to"] == "2026-08-15"
        assert energy_daily["max_gap_seconds"] == "300"

        event_params = next(
            params for path, params in seen if path == "/v1/systems/sys_default/events"
        )
        assert event_params["limit"] == "1000"

    asyncio.run(scenario())
