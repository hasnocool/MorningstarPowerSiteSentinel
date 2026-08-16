"""FastAPI application for PowerSite Sentinel."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from powersite_sentinel import __version__
from powersite_sentinel.client import MorningstarApiClient, MorningstarApiError
from powersite_sentinel.config import Settings
from powersite_sentinel.incidents import IncidentStore
from powersite_sentinel.service import SentinelService

_TIMELINE_CATEGORY_PATTERN = (
    "^(communications|charge|fault|alarm|history|energy|incident|system)$"
)


def create_app(settings: Settings, service: SentinelService | None = None) -> FastAPI:
    sentinel = service or SentinelService(
        MorningstarApiClient(
            base_url=settings.morningstar_base_url,
            timeout_seconds=settings.morningstar_timeout_seconds,
        ),
        IncidentStore(settings.database_path),
        settings,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.monitor_enabled:
            sentinel.start_monitor()
        yield
        await sentinel.stop_monitor()

    app = FastAPI(
        title="Morningstar PowerSite Sentinel",
        version=__version__,
        description="Local-first, read-only site observability and forensic diagnostics.",
        lifespan=lifespan,
    )
    app.state.sentinel = sentinel

    web_dir = Path(__file__).with_name("web")
    app.mount("/assets", StaticFiles(directory=web_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @app.get("/health")
    async def health() -> dict[str, object]:
        upstream: dict[str, object]
        try:
            upstream = await sentinel.client.health()
            upstream_state = "reachable"
        except MorningstarApiError as exc:
            upstream = {"error": str(exc)}
            upstream_state = "unreachable"
        return {
            "status": "ok",
            "version": __version__,
            "upstream": upstream_state,
            "upstream_health": upstream,
        }

    @app.get("/v1/sites")
    async def sites() -> list[dict[str, object]]:
        try:
            return await sentinel.list_sites()
        except MorningstarApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/v1/sites/{site_uid}/assessment")
    async def assessment(site_uid: str) -> dict[str, object]:
        try:
            return await sentinel.assess_site(site_uid)
        except MorningstarApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/v1/sites/{site_uid}/explain")
    async def explain(site_uid: str) -> dict[str, object]:
        try:
            return await sentinel.explain_site(site_uid)
        except MorningstarApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/v1/sites/{site_uid}/forensics")
    async def forensics(
        site_uid: str,
        days: int | None = Query(None, ge=1, le=366),
        max_gap_seconds: int = Query(300, ge=1, le=3600),
        event_limit: int | None = Query(None, ge=1, le=5000),
        refresh: bool = Query(False),
    ) -> dict[str, object]:
        try:
            return await sentinel.forensic_report(
                site_uid,
                days=days,
                max_gap_seconds=max_gap_seconds,
                event_limit=event_limit,
                refresh=refresh,
            )
        except MorningstarApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/sites/{site_uid}/timeline")
    async def timeline(
        site_uid: str,
        days: int | None = Query(None, ge=1, le=366),
        max_gap_seconds: int = Query(300, ge=1, le=3600),
        limit: int = Query(500, ge=1, le=5000),
        category: str | None = Query(None, pattern=_TIMELINE_CATEGORY_PATTERN),
    ) -> dict[str, object]:
        try:
            return await sentinel.timeline(
                site_uid,
                days=days,
                max_gap_seconds=max_gap_seconds,
                limit=limit,
                category=category,
            )
        except MorningstarApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/sites/{site_uid}/incidents")
    async def site_incidents(
        site_uid: str,
        status: str | None = Query("open", pattern="^(open|resolved)$"),
        limit: int = Query(200, ge=1, le=5000),
    ) -> list[dict[str, object]]:
        return await sentinel.incidents(site_uid=site_uid, status=status, limit=limit)

    @app.get("/v1/incidents")
    async def incidents(
        status: str | None = Query(None, pattern="^(open|resolved)$"),
        limit: int = Query(200, ge=1, le=5000),
    ) -> list[dict[str, object]]:
        return await sentinel.incidents(status=status, limit=limit)

    return app
