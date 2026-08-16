"""Sentinel orchestration: live health plus historical forensic diagnostics."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from powersite_sentinel.client import MorningstarApiClient
from powersite_sentinel.config import Settings
from powersite_sentinel.forensics import (
    evaluate_forensic_findings,
    forensic_period,
    observable_forensic_fingerprints,
    site_forensic_summary,
    summarize_controller_history,
)
from powersite_sentinel.health import calculate_scores
from powersite_sentinel.incidents import IncidentStore
from powersite_sentinel.rules import evaluate_findings, observable_incident_fingerprints
from powersite_sentinel.timeline import build_unified_timeline


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
        self._forensic_cache: dict[
            tuple[str, int, int, int],
            tuple[datetime, dict[str, object]],
        ] = {}
        self._monitor_task: asyncio.Task[None] | None = None
        self._forensic_task: asyncio.Task[None] | None = None

    async def list_sites(self) -> list[dict[str, object]]:
        return await self.client.list_sites()

    async def assess_site(self, site_uid: str) -> dict[str, object]:
        snapshot = await self.client.site_snapshot(site_uid)
        now = datetime.now(UTC)
        findings = evaluate_findings(snapshot, self.settings, now=now)
        health = calculate_scores(snapshot, findings, self.settings, now=now)
        resolvable = observable_incident_fingerprints(snapshot)
        open_incidents = await self.store.reconcile(
            site_uid,
            findings,
            resolvable_fingerprints=resolvable,
        )
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
        *,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        return await self.store.list(site_uid=site_uid, status=status, limit=limit)

    async def forensic_report(
        self,
        site_uid: str,
        *,
        days: int | None = None,
        max_gap_seconds: int = 300,
        event_limit: int | None = None,
        refresh: bool = False,
    ) -> dict[str, object]:
        window_days = days if days is not None else self.settings.forensic_window_days
        timeline_limit = event_limit if event_limit is not None else self.settings.forensic_event_limit
        if not 1 <= window_days <= 366:
            raise ValueError("forensic window days must be between 1 and 366")
        if not 1 <= max_gap_seconds <= 3600:
            raise ValueError("max_gap_seconds must be between 1 and 3600")
        if not 1 <= timeline_limit <= 5000:
            raise ValueError("event_limit must be between 1 and 5000")

        now = datetime.now(UTC)
        cache_key = (site_uid, window_days, max_gap_seconds, timeline_limit)
        cached = self._forensic_cache.get(cache_key)
        if cached is not None and not refresh:
            cached_at, report = cached
            age = (now - cached_at).total_seconds()
            if age <= self.settings.forensic_cache_seconds:
                return report

        start, end = forensic_period(window_days, now=now)
        raw = await self.client.site_forensic_snapshot(
            site_uid,
            start=start,
            end=end,
            max_gap_seconds=max_gap_seconds,
            event_limit=timeline_limit,
        )
        controllers = [
            dict(item)
            for item in raw.get("controllers", [])
            if isinstance(item, dict)
        ]
        history = raw.get("history") if isinstance(raw.get("history"), dict) else {}

        controller_reports: list[dict[str, object]] = []
        for controller in controllers:
            uid = str(controller.get("controller_uid") or "")
            bundle = history.get(uid) if isinstance(history, dict) else None
            if not uid or not isinstance(bundle, dict):
                continue
            controller_reports.append(
                summarize_controller_history(
                    controller,
                    bundle,
                    self.settings,
                )
            )

        findings = evaluate_forensic_findings(controller_reports, self.settings)
        resolvable = observable_forensic_fingerprints(controller_reports)
        open_incidents = await self.store.reconcile(
            site_uid,
            findings,
            resolvable_fingerprints=resolvable,
        )
        incident_history = await self.store.list(
            site_uid=site_uid,
            status=None,
            limit=min(timeline_limit, 5000),
        )
        upstream_events = [
            dict(item)
            for item in raw.get("events", [])
            if isinstance(item, dict)
        ]
        timeline = build_unified_timeline(
            site_uid,
            upstream_events,
            controllers,
            controller_reports,
            incident_history,
            limit=timeline_limit,
        )
        report = {
            "site_uid": site_uid,
            "generated_at": now.isoformat(),
            "period": {
                "from": start,
                "to": end,
                "days": window_days,
                "semantics": "complete UTC controller days; inclusive start, exclusive end",
            },
            "summary": site_forensic_summary(controller_reports),
            "controllers": controller_reports,
            "findings": [item.to_dict() for item in findings],
            "open_incidents": open_incidents,
            "timeline": timeline,
            "evidence_policy": (
                "Recovered controller daily records improve day-level continuity without "
                "reconstructing missing high-frequency samples. Controller energy counters "
                "and bounded local integrations remain separate evidence classes."
            ),
        }
        self._forensic_cache[cache_key] = (now, report)
        return report

    async def timeline(
        self,
        site_uid: str,
        *,
        days: int | None = None,
        max_gap_seconds: int = 300,
        limit: int = 500,
        category: str | None = None,
    ) -> dict[str, object]:
        report = await self.forensic_report(
            site_uid,
            days=days,
            max_gap_seconds=max_gap_seconds,
            event_limit=min(5000, max(limit, self.settings.forensic_event_limit)),
        )
        timeline = report.get("timeline") if isinstance(report.get("timeline"), dict) else {}
        events = [
            dict(item)
            for item in timeline.get("events", [])
            if isinstance(item, dict)
            and (category is None or item.get("category") == category)
        ]
        bounded = events[:limit]
        return {
            "site_uid": site_uid,
            "period": report.get("period"),
            "count": len(bounded),
            "category": category,
            "events": bounded,
            "semantics": timeline.get("semantics"),
        }

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

        priority = [
            item
            for item in findings
            if isinstance(item, dict) and item.get("severity") != "info"
        ]
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
        if self._forensic_task is None or self._forensic_task.done():
            self._forensic_task = asyncio.create_task(self._forensic_monitor_loop())

    async def stop_monitor(self) -> None:
        tasks = [task for task in (self._monitor_task, self._forensic_task) if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._monitor_task = None
        self._forensic_task = None

    async def _monitor_loop(self) -> None:
        while True:
            try:
                await self.assess_all()
            except Exception:
                # The HTTP health endpoint exposes upstream availability. The monitor must survive outages.
                pass
            await asyncio.sleep(self.settings.poll_interval_seconds)

    async def _forensic_monitor_loop(self) -> None:
        while True:
            try:
                for site in await self.list_sites():
                    uid = str(site.get("system_uid") or site.get("name") or "")
                    if uid:
                        await self.forensic_report(uid, refresh=True)
            except Exception:
                # Historical diagnostics must not stop live health monitoring during upstream outages.
                pass
            await asyncio.sleep(self.settings.forensic_poll_interval_seconds)
