"""Run the web app: ``uv run python -m project_nurilab.web``."""

from __future__ import annotations

import logging
import sys

import uvicorn

from project_nurilab.web.app import create_app
from project_nurilab.web.settings import WebSettings


def main() -> int:
    """Start uvicorn on NURILAB_WEB_HOST:NURILAB_WEB_PORT."""

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        settings = WebSettings.from_env()
    except ValueError as exc:
        print(f"nurilab web: {exc}", file=sys.stderr)
        return 2
    # Bind is read here, not by "uvicorn ...:app", so the app decides it.
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
