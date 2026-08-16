"""Read-only adapter for MorningstarModbusAPI."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx


class MorningstarApiError(RuntimeError):
    """Raised when the upstream Morningstar API cannot satisfy a read."""


@dataclass(slots=True)
class MorningstarApiClient:
    base_url: str
    timeout_seconds: float = 5.0
    transport: httpx.AsyncBaseTransport | None = None

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, object] | None = None,
    ) -> object:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(path, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MorningstarApiError(f"GET {path} failed: {exc}") from exc

    async def health(self) -> dict[str, object]:
        payload = await self._get("/health")
        return payload if isinstance(payload, dict) else {}

    async def list_sites(self) -> list[dict[str, object]]:
        payload = await self._get("/v1/systems")
        return [dict(item) for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    async def site_snapshot(self, site_uid: str) -> dict[str, object]:
        paths = {
            "site": f"/v1/systems/{site_uid}",
            "controllers": f"/v1/systems/{site_uid}/controllers",
            "latest": f"/v1/systems/{site_uid}/latest",
            "power_flow": f"/v1/systems/{site_uid}/power-flow",
            "energy_ledger": f"/v1/systems/{site_uid}/energy-ledger",
            "component_graph": f"/v1/systems/{site_uid}/component-graph",
            "events": f"/v1/systems/{site_uid}/events?limit=100",
        }
        keys = list(paths)
        values = await asyncio.gather(*(self._get(paths[key]) for key in keys))
        return {key: value for key, value in zip(keys, values, strict=True)}

    async def controller_history_bundle(
        self,
        controller_uid: str,
        *,
        start: str,
        end: str,
        max_gap_seconds: int,
    ) -> dict[str, object]:
        date_params = {"from": start, "to": end}
        energy_params = {
            "from": start,
            "to": end,
            "max_gap_seconds": max_gap_seconds,
        }
        coverage, gaps, energy_daily, energy_summary = await asyncio.gather(
            self._get(
                f"/v1/controllers/{controller_uid}/history/coverage",
                params=date_params,
            ),
            self._get(
                f"/v1/controllers/{controller_uid}/history/gaps",
                params=date_params,
            ),
            self._get(
                f"/v1/controllers/{controller_uid}/energy/daily",
                params=energy_params,
            ),
            self._get(
                f"/v1/controllers/{controller_uid}/energy/summary",
                params=energy_params,
            ),
        )
        return {
            "coverage": coverage if isinstance(coverage, dict) else {},
            "gaps": gaps if isinstance(gaps, dict) else {},
            "energy_daily": energy_daily if isinstance(energy_daily, dict) else {},
            "energy_summary": energy_summary if isinstance(energy_summary, dict) else {},
        }

    async def site_forensic_snapshot(
        self,
        site_uid: str,
        *,
        start: str,
        end: str,
        max_gap_seconds: int,
        event_limit: int,
    ) -> dict[str, object]:
        controllers_payload, events_payload = await asyncio.gather(
            self._get(f"/v1/systems/{site_uid}/controllers"),
            self._get(
                f"/v1/systems/{site_uid}/events",
                params={
                    "from": f"{start}T00:00:00+00:00",
                    "to": f"{end}T00:00:00+00:00",
                    "limit": event_limit,
                },
            ),
        )
        controllers = (
            [dict(item) for item in controllers_payload if isinstance(item, dict)]
            if isinstance(controllers_payload, list)
            else []
        )
        events = (
            [dict(item) for item in events_payload if isinstance(item, dict)]
            if isinstance(events_payload, list)
            else []
        )

        history: dict[str, dict[str, object]] = {}
        controller_uids = [
            str(item.get("controller_uid") or "")
            for item in controllers
            if item.get("controller_uid")
        ]
        bundles = await asyncio.gather(
            *(
                self.controller_history_bundle(
                    uid,
                    start=start,
                    end=end,
                    max_gap_seconds=max_gap_seconds,
                )
                for uid in controller_uids
            )
        )
        for uid, bundle in zip(controller_uids, bundles, strict=True):
            history[uid] = bundle

        return {
            "site_uid": site_uid,
            "controllers": controllers,
            "events": events,
            "history": history,
            "period": {"from": start, "to": end},
        }
