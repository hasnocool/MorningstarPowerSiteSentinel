"""Configuration loading for PowerSite Sentinel."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    morningstar_base_url: str = "http://127.0.0.1:8080"
    morningstar_timeout_seconds: float = 5.0
    database_path: str = "./data/sentinel.db"
    poll_interval_seconds: float = 15.0
    monitor_enabled: bool = True
    stale_after_seconds: float = 45.0
    residual_warning_w: float = 50.0
    residual_warning_percent: float = 8.0
    residual_critical_percent: float = 20.0
    soc_warning_percent: float = 30.0
    soc_critical_percent: float = 15.0
    bind_host: str = "127.0.0.1"
    bind_port: int = 8090


def _section(data: dict[str, object], name: str) -> dict[str, object]:
    value = data.get(name)
    return value if isinstance(value, dict) else {}


def load_settings(path: str | None = None) -> Settings:
    settings = Settings()
    if path:
        with Path(path).open("rb") as handle:
            data = tomllib.load(handle)
        morningstar = _section(data, "morningstar")
        sentinel = _section(data, "sentinel")
        server = _section(data, "server")
        settings = replace(
            settings,
            morningstar_base_url=str(morningstar.get("base_url", settings.morningstar_base_url)).rstrip("/"),
            morningstar_timeout_seconds=float(
                morningstar.get("timeout_seconds", settings.morningstar_timeout_seconds)
            ),
            database_path=str(sentinel.get("database_path", settings.database_path)),
            poll_interval_seconds=float(
                sentinel.get("poll_interval_seconds", settings.poll_interval_seconds)
            ),
            monitor_enabled=bool(sentinel.get("monitor_enabled", settings.monitor_enabled)),
            stale_after_seconds=float(
                sentinel.get("stale_after_seconds", settings.stale_after_seconds)
            ),
            residual_warning_w=float(
                sentinel.get("residual_warning_w", settings.residual_warning_w)
            ),
            residual_warning_percent=float(
                sentinel.get("residual_warning_percent", settings.residual_warning_percent)
            ),
            residual_critical_percent=float(
                sentinel.get("residual_critical_percent", settings.residual_critical_percent)
            ),
            soc_warning_percent=float(
                sentinel.get("soc_warning_percent", settings.soc_warning_percent)
            ),
            soc_critical_percent=float(
                sentinel.get("soc_critical_percent", settings.soc_critical_percent)
            ),
            bind_host=str(server.get("host", settings.bind_host)),
            bind_port=int(server.get("port", settings.bind_port)),
        )

    env_map: tuple[tuple[str, str, object], ...] = (
        ("SENTINEL_MORNINGSTAR_URL", "morningstar_base_url", str),
        ("SENTINEL_DATABASE_PATH", "database_path", str),
        ("SENTINEL_POLL_INTERVAL", "poll_interval_seconds", float),
        ("SENTINEL_HOST", "bind_host", str),
        ("SENTINEL_PORT", "bind_port", int),
    )
    updates: dict[str, object] = {}
    for env_name, field_name, converter in env_map:
        value = os.getenv(env_name)
        if value is not None:
            converted = converter(value)  # type: ignore[operator]
            if field_name == "morningstar_base_url":
                converted = str(converted).rstrip("/")
            updates[field_name] = converted
    return replace(settings, **updates) if updates else settings
