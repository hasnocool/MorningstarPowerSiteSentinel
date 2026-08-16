"""Sentinel orchestration: fetch, assess, persist incidents, explain."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from powersite_sentinel.client import MorningstarApiClient
from powersite_sentinel.config import Settings
from powersite_sentinel.health import calculate_scores
from powersite_sentinel.incidents import IncidentStore
from powersite_sentinel.rules import evaluate_findings


def _value(payload: object) -> float | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class SentinelService:
    def __init__(
        self,
        client: MorningstarApiClient,
        store: IncidentStore,
        settings: Settings,
    ) -> None:
        self.client = client
        self.store = store
        self.settings = settings
        self._cache: dict[str, dict[str, object]] = {}
        self._monitor_task: asyncio.Task[None] | None = None

    async def list_sites(self) -> list[dict[str, object]]:
        return await self.client.list_sites()

    async def assess_site(self, site_uid: str) -> dict[str, object]:
        snapshot = await self.client.site_snapshot(site_uid)
        now = datetime.now(UTC)
        findings = evaluate_findings(snapshot, self.settings, now=now)
        health = calculate_scores(snapshot, findings, self.settings, now=now)
        open_incidents = await self.store.reconcile(site_uid, findings)
        assessment = {
            "site_uid": site_uid,
            "assessed_at": now.isoformat(),
            "health": health,
            "findings": [item.to_dict() for item in findings],
            "open_incidents": open_incidents,
            "snapshot": snapshot,
        }
        self._cache[site_uid] = assessment
        return assessment

    async def assess_all(self) -> list[dict[str, object]]:
        sites = await self.list_sites()
        assessments: list[dict[str, object]] = []
        for site in sites:
            uid = str(site.get("system_uid") or site.get("name") or "")
            if not uid:
                continue
            assessments.append(await self.assess_site(uid))
        return assessments

    async def incidents(
        self,
        site_uid: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        return await self.store.list(site_uid=site_uid, status=status)

    async def explain_site(self, site_uid: str) -> dict[str, object]:
        assessment = self._cache.get(site_uid) or await self.assess_site(site_uid)
        snapshot = assessment.get("snapshot") if isinstance(assessment.get("snapshot"), dict) else {}
        flow = snapshot.get("power_flow") if isinstance(snapshot.get("power_flow"), dict) else {}
        sources = flow.get("sources") if isinstance(flow.get("sources"), dict) else {}
        battery = flow.get("battery") if isinstance(flow.get("battery"), dict) else {}
        loads = flow.get("loads") if isinstance(flow.get("loads"), dict) else {}
        findings = assessment.get("findings") if isinstance(assessment.get("findings"), list) else []

        solar = _value(sources.get("solar_input_power_w"))
        battery_w = _value(battery.get("net_power_w"))
        load_w = _value(loads.get("dc_power_w"))
        flow_parts: list[str] = []
        if solar is not None:
            flow_parts.append(f"solar input is {solar:.0f} W")
        if load_w is not None:
            flow_parts.append(f"measured DC loads are {load_w:.0f} W")
        if battery_w is not None:
            direction = "charging" if battery_w >= 0 else "discharging"
            flow_parts.append(f"battery net flow is {abs(battery_w):.0f} W {direction}")

        priority = [item for item in findings if isinstance(item, dict) and item.get("severity") != "info"]
        if priority:
            headline = str(priority[0].get("summary") or priority[0].get("title"))
        elif flow_parts:
            headline = "No evidence-backed warning or critical condition is active."
        else:
            headline = "The site is reachable, but current electrical visibility is limited."

        return {
            "site_uid": site_uid,
            "headline": headline,
            "flow_summary": (
                "; ".join(flow_parts)
                if flow_parts
                else "No complete live power-flow summary is available."
            ),
            "important_findings": priority[:5],
            "evidence_policy": (
                "Sentinel explains only source-backed upstream observations and explicit local derivations; "
                "unknown measurements remain unknown."
            ),
        }

    def start_monitor(self) -> None:
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitor(self) -> None:
        if self._monitor_task is None:
            return
        self._monitor_task.cancel()
        try:
            await self._monitor_task
        except asyncio.CancelledError:
            pass
        self._monitor_task = None

    async def _monitor_loop(self) -> None:
        while True:
            try:
                await self.assess_all()
            except Exception:
                # The HTTP health endpoint exposes upstream availability. The monitor must survive outages.
                pass
            await asyncio.sleep(self.settings.poll_interval_seconds)
