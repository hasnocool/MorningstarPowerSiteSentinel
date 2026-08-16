"""FastAPI application for PowerSite Sentinel."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from powersite_sentinel import __version__
from powersite_sentinel.client import MorningstarApiClient, MorningstarApiError
from powersite_sentinel.config import Settings
from powersite_sentinel.incidents import IncidentStore
from powersite_sentinel.service import SentinelService


def create_app(settings: Settings, service: SentinelService | None = None) -> FastAPI:
    sentinel = service or SentinelService(
        MorningstarApiClient(
            base_url=settings.morningstar_base_url,
            timeout_seconds=settings.morningstar_timeout_seconds,
            connect_attempts=settings.morningstar_connect_attempts,
            retry_backoff_seconds=settings.morningstar_retry_backoff_seconds,
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
        description="Local-first, read-only site observability and incident intelligence.",
        lifespan=lifespan,
    )
    app.state.sentinel = sentinel

    @app.middleware("http")
    async def disable_web_cache(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

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

    @app.get("/v1/controllers/{controller_uid}/detail")
    async def controller_detail(controller_uid: str) -> dict[str, object]:
        try:
            return await sentinel.controller_detail(controller_uid)
        except MorningstarApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/v1/sites/{site_uid}/incidents")
    async def site_incidents(
        site_uid: str,
        status: str | None = Query("open", pattern="^(open|resolved)$"),
    ) -> list[dict[str, object]]:
        return await sentinel.incidents(site_uid=site_uid, status=status)

    @app.get("/v1/incidents")
    async def incidents(
        status: str | None = Query(None, pattern="^(open|resolved)$"),
    ) -> list[dict[str, object]]:
        return await sentinel.incidents(status=status)

    return app
