from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .database import (
    create_backup,
    database_integrity,
    list_backups,
    connect,
    migrate,
)
from .repository import asset_detail, catalog_summary, recent_events, search_assets


@dataclass(frozen=True)
class AppSettings:
    db_path: Path
    backup_dir: Path


def create_app(settings: AppSettings) -> FastAPI:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    with connect(settings.db_path) as connection:
        migrate(connection)

    app = FastAPI(
        title="ATLAS Beacon API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.backup_lock = threading.Lock()
    web_dir = Path(__file__).resolve().parent / "web"
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(web_dir / "index.html")

    @app.get("/api/health")
    def health():
        integrity = database_integrity(settings.db_path)
        return {
            "service": "Beacon",
            "version": __version__,
            "local_only": True,
            "database": integrity,
        }

    @app.get("/api/summary")
    def summary():
        return catalog_summary(settings.db_path)

    @app.get("/api/assets")
    def assets(
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        return search_assets(
            settings.db_path,
            query=q,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/assets/{asset_id}")
    def detail(asset_id: str):
        result = asset_detail(settings.db_path, asset_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return result

    @app.get("/api/events")
    def events(limit: int = Query(default=20, ge=1, le=100)):
        return {"items": recent_events(settings.db_path, limit)}

    @app.get("/api/backups")
    def backups():
        return {"items": list_backups(settings.backup_dir)}

    @app.post("/api/backups", status_code=201)
    def backup(x_atlas_action: str = Header(default="")):
        if x_atlas_action != "create-backup":
            raise HTTPException(
                status_code=403,
                detail="Explicit local action header required",
            )
        if not app.state.backup_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="A backup is already running")
        try:
            return create_backup(settings.db_path, settings.backup_dir)
        finally:
            app.state.backup_lock.release()

    return app
