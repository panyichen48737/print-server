"""Global state shared between GUI pages and launcher entry point."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.config import Config
    from launcher._server import ServerHandle

server: ServerHandle | None = None
app: FastAPI | None = None
config: Config | Any | None = None
