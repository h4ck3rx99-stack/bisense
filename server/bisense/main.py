"""FastAPI application: API routes, security headers, error handling, SPA serving, startup warm-up.

In production/demo one process serves both the API (/api/...) and the built React app (web/dist),
so there is one port and one thing to start.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from bisense.api import ask as ask_api
from bisense.api import misc as misc_api
from bisense.api import standards as standards_api
from bisense.api.common import ApiError
from bisense.config import REPO_ROOT, get_settings

WEB_DIST = REPO_ROOT / "web" / "dist"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if msg.startswith("{"):
            return msg
        return json.dumps({"level": record.levelname, "logger": record.name, "msg": msg}, ensure_ascii=False)


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("bisense")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False


def warm_up() -> None:
    """Load the index and models and run one query so the first real request is fast."""
    log = logging.getLogger("bisense.startup")
    try:
        from bisense.retrieval.embed import embed_query
        from bisense.retrieval.index import db_conn, get_index
        from bisense.retrieval.query import understand
        from bisense.retrieval.search import search

        idx = get_index()
        embed_query("warm up")
        conn = db_conn()
        try:
            search(conn, understand(conn, "packaged drinking water requirements"), rerank_enabled=get_settings().rerank_enabled)
        finally:
            conn.close()
        log.info(json.dumps({"event": "warm_up_done", "index_version": idx.version, "chunks": idx.counts.get("chunks")}))
    except Exception as exc:  # the app must still start (e.g. before the first ingest)
        log.warning(json.dumps({"event": "warm_up_skipped", "reason": exc.__class__.__name__, "detail": str(exc)[:200]}))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    s = get_settings()
    if not s.llm_configured or s.llm_provider == "none":
        logging.getLogger("bisense.startup").warning(json.dumps({"event": "no_llm", "msg": "No LLM configured: answers use extractive mode (verbatim clauses). See .env.example."}))
    threading.Thread(target=warm_up, daemon=True).start()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="BISense API", version="0.1.0", lifespan=lifespan, docs_url="/api/docs" if s.debug else None, redoc_url=None, openapi_url="/api/openapi.json")

    if s.app_env == "development":
        app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "font-src 'self' data:; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
        return response

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content={"code": exc.code, "message_key": exc.message_key})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in e.get("loc", [])[1:]) for e in exc.errors()][:5]
        return JSONResponse(status_code=422, content={"code": "invalid_request", "message_key": "error.invalid_request", "fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and not request.url.path.startswith("/api") and (WEB_DIST / "index.html").exists():
            return FileResponse(WEB_DIST / "index.html")
        return JSONResponse(status_code=exc.status_code, content={"code": "not_found" if exc.status_code == 404 else "http_error", "message_key": "error.not_found" if exc.status_code == 404 else "error.internal"})

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logging.getLogger("bisense.api").exception("unhandled error")
        return JSONResponse(status_code=500, content={"code": "internal", "message_key": "error.internal"})

    app.include_router(misc_api.router)
    app.include_router(ask_api.router)
    app.include_router(standards_api.router)

    if (WEB_DIST / "index.html").exists():
        assets = WEB_DIST / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse(status_code=404, content={"code": "not_found", "message_key": "error.not_found"})
            candidate = (WEB_DIST / path).resolve()
            if path and candidate.is_file() and WEB_DIST.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(WEB_DIST / "index.html")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    s = get_settings()
    uvicorn.run("bisense.main:app", host=s.host, port=s.port, reload=False, log_level="warning")


if __name__ == "__main__":
    run()
