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

    async def _get(self, path: str) -> object:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(path)
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
