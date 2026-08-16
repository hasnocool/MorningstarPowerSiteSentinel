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
    connect_attempts: int = 5
    retry_backoff_seconds: float = 0.25
    transport: httpx.AsyncBaseTransport | None = None

    async def _get(self, path: str) -> object:
        attempts = max(1, self.connect_attempts)
        last_connect_error: httpx.HTTPError | None = None

        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = await client.get(path)
                    response.raise_for_status()
                    return response.json()
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_connect_error = exc
                if attempt >= attempts:
                    break
                delay = self.retry_backoff_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(max(0.0, delay))
            except (httpx.HTTPError, ValueError) as exc:
                raise MorningstarApiError(f"GET {path} failed: {exc}") from exc

        assert last_connect_error is not None
        raise MorningstarApiError(
            f"GET {path} failed after {attempts} connection attempts: {last_connect_error}. "
            "Verify MorningstarModbusAPI is running with the `run` or `serve` command and that "
            "SENTINEL_MORNINGSTAR_URL points at its HTTP listener."
        ) from last_connect_error

    async def _get_optional(self, path: str) -> object:
        """Read an enrichment surface without making the whole inspection fail."""
        try:
            return await self._get(path)
        except MorningstarApiError as exc:
            return {"status": "unavailable", "error": str(exc)}

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

    async def controller_snapshot(self, controller_uid: str) -> dict[str, object]:
        """Fetch rich controller detail only when an operator opens that controller."""
        controller = await self._get(f"/v1/controllers/{controller_uid}")
        paths = {
            "latest": f"/v1/controllers/{controller_uid}/latest",
            "history_summary": f"/v1/controllers/{controller_uid}/history/summary",
            "daily_summary": f"/v1/controllers/{controller_uid}/history/controller-daily/summary",
            "history_coverage": f"/v1/controllers/{controller_uid}/history/coverage",
            "polling_performance": (
                f"/v1/controllers/{controller_uid}/polling/performance?window=300&mode=watch"
            ),
        }
        keys = list(paths)
        values = await asyncio.gather(*(self._get_optional(paths[key]) for key in keys))
        return {
            "controller": controller if isinstance(controller, dict) else {},
            **{key: value for key, value in zip(keys, values, strict=True)},
        }
