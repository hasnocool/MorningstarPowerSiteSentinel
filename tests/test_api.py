from fastapi.testclient import TestClient

from powersite_sentinel.api import create_app
from powersite_sentinel.config import Settings


class FakeClient:
    async def health(self):
        return {"status": "ok", "version": "0.6.0"}


class FakeService:
    def __init__(self):
        self.client = FakeClient()

    def start_monitor(self):
        return None

    async def stop_monitor(self):
        return None

    async def list_sites(self):
        return [{"system_uid": "sys_default", "name": "default", "controller_count": 1}]

    async def assess_site(self, site_uid):
        return {"site_uid": site_uid, "health": {"overall": {"value": 100}}, "findings": []}

    async def explain_site(self, site_uid):
        return {"site_uid": site_uid, "headline": "Healthy"}

    async def controller_detail(self, controller_uid):
        return {
            "controller_uid": controller_uid,
            "snapshot": {"controller": {"controller_uid": controller_uid}},
        }

    async def forensic_report(
        self,
        site_uid,
        *,
        days=None,
        max_gap_seconds=300,
        event_limit=None,
        refresh=False,
    ):
        return {
            "site_uid": site_uid,
            "period": {"days": days or 30},
            "summary": {"missing_controller_days": 0},
            "timeline": {"events": []},
        }

    async def timeline(
        self,
        site_uid,
        *,
        days=None,
        max_gap_seconds=300,
        limit=500,
        category=None,
    ):
        return {
            "site_uid": site_uid,
            "period": {"days": days or 30},
            "count": 0,
            "category": category,
            "events": [],
        }

    async def incidents(self, site_uid=None, status=None, *, limit=200):
        return []


def test_read_only_product_api() -> None:
    app = create_app(Settings(monitor_enabled=False), service=FakeService())
    with TestClient(app) as client:
        assert client.get("/health").json()["upstream"] == "reachable"
        assert client.get("/v1/sites").json()[0]["system_uid"] == "sys_default"
        assert client.get("/v1/sites/sys_default/assessment").status_code == 200
        detail = client.get("/v1/controllers/controller_a/detail")
        assert detail.status_code == 200
        assert detail.json()["controller_uid"] == "controller_a"
        assert client.get("/v1/sites/sys_default/forensics?days=14").status_code == 200
        assert (
            client.get("/v1/sites/sys_default/timeline?category=communications").status_code
            == 200
        )
        assert client.post("/v1/sites/sys_default/assessment").status_code == 405
        assert client.post("/v1/sites/sys_default/forensics").status_code == 405
        assert client.post("/v1/sites/sys_default/timeline").status_code == 405


def test_dashboard_assets_are_not_cached_across_deployments() -> None:
    app = create_app(Settings(monitor_enabled=False), service=FakeService())
    with TestClient(app) as client:
        index = client.get("/")
        script = client.get("/assets/app.js")

    assert index.status_code == 200
    assert script.status_code == 200
    assert index.headers["cache-control"] == "no-store, max-age=0"
    assert script.headers["cache-control"] == "no-store, max-age=0"
    assert "controller telemetry" in index.text
    assert "refinements.js" not in index.text