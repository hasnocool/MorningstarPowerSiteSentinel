"""Command-line entry point for Sentinel."""

from __future__ import annotations

import argparse

import uvicorn

from powersite_sentinel.api import create_app
from powersite_sentinel.config import load_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="powersite-sentinel")
    parser.add_argument("--config", help="Path to Sentinel TOML configuration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve", help="Run the Sentinel daemon and local web UI")
    return parser


def main() -> None:
    args = _parser().parse_args()
    settings = load_settings(args.config)
    if args.command == "serve":
        uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.bind_port)
