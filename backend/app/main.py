"""Better Anki Web server.

Run with a single worker (the collection is single-writer):
    uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anki.errors import BackendError, InvalidInput, NotFoundError
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import Auth
from .collection import CollectionManager, CollectionUnavailable
from .config import Settings
from .routes import auth, decks, media, notes, review, sync
from .sync import SyncManager

log = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cm = CollectionManager(settings.collection_path)
    sync_manager = SyncManager(cm, settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        cm.open()
        sync_manager.start()
        try:
            yield
        finally:
            sync_manager.stop()
            cm.close()

    app = FastAPI(
        title="Better Anki Web",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.auth = Auth(settings)
    app.state.cm = cm
    app.state.sync = sync_manager

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    _install_error_handlers(app)

    for module in (auth, sync, decks, review, notes, media):
        app.include_router(module.router)

    _mount_frontend(app, settings)
    return app


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(CollectionUnavailable)
    async def unavailable(_request: Request, err: CollectionUnavailable) -> JSONResponse:
        return JSONResponse({"detail": "The collection is busy syncing. Try again shortly."}, 503)

    @app.exception_handler(NotFoundError)
    async def not_found(_request: Request, err: NotFoundError) -> JSONResponse:
        return JSONResponse({"detail": str(err) or "Not found."}, 404)

    @app.exception_handler(InvalidInput)
    async def invalid(_request: Request, err: InvalidInput) -> JSONResponse:
        return JSONResponse({"detail": str(err)}, 400)

    @app.exception_handler(BackendError)
    async def backend_error(_request: Request, err: BackendError) -> JSONResponse:
        log.exception("Anki backend error", exc_info=err)
        return JSONResponse({"detail": str(err) or "Anki error."}, 500)


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    dist = settings.resolved_frontend_dist()
    index = dist / "index.html"
    if not index.exists():
        log.warning("Frontend not built (%s missing); serving the API only.", index)
        return

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def spa(path: str) -> FileResponse | JSONResponse:
        if path.startswith(("api/", "media/")):
            return JSONResponse({"detail": "Not found."}, 404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
