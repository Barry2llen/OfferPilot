from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Match
from starlette.staticfiles import StaticFiles

FRONTEND_DIST_ENV = "OFFER_PILOT_FRONTEND_DIST"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRONTEND_DIST = BACKEND_ROOT.parent / "frontend" / "dist"
SPA_NAVIGATION_PATHS = {
    "/files",
    "/resumes",
    "/job-descriptions",
    "/settings",
    "/settings/providers",
    "/settings/selections",
}


class SpaStaticFiles(StaticFiles):
    """Serve built SPA assets and fall back to the entry document for navigation."""

    async def get_response(self, path: str, scope: dict) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or not self._is_spa_navigation(path, scope):
                raise
            return await self._get_entry_response(scope)

        if response.status_code == 404 and self._is_spa_navigation(path, scope):
            return await self._get_entry_response(scope)
        if (
            response.status_code < 400
            and response.headers.get("content-type", "").startswith("text/html")
            and not (path and Path(path).suffix)
        ):
            return _mark_spa_entry(response)
        return response

    async def _get_entry_response(self, scope: dict) -> Response:
        return _mark_spa_entry(await super().get_response("index.html", scope))

    @staticmethod
    def _is_spa_navigation(path: str, scope: dict) -> bool:
        if scope["method"] not in {"GET", "HEAD"}:
            return False
        if path and Path(path).suffix:
            return False

        return not path or _is_document_navigation(Headers(scope=scope))


def resolve_frontend_dist(frontend_dist: Path | str | None = None) -> Path | None:
    """Find a built frontend without making its presence mandatory for API startup."""

    configured_path = frontend_dist or os.getenv(FRONTEND_DIST_ENV)
    candidate = (
        Path(configured_path).expanduser().resolve()
        if configured_path
        else DEFAULT_FRONTEND_DIST
    )
    return candidate if (candidate / "index.html").is_file() else None


def mount_frontend(
    app: FastAPI, frontend_dist: Path | str | None = None
) -> Path | None:
    resolved_dist = resolve_frontend_dist(frontend_dist)
    app.state.frontend_dist = resolved_dist

    if resolved_dist is not None:
        index_path = resolved_dist / "index.html"

        @app.middleware("http")
        async def serve_spa_navigation(request: Request, call_next):
            if _is_api_path_used_as_spa_navigation(request):
                return _mark_spa_entry(FileResponse(index_path))

            response = await call_next(request)
            if response.status_code == 405 and not _matches_non_frontend_route(
                app,
                request.scope,
            ):
                # The root static mount accepts every path. Keep unknown API-like
                # requests as 404 instead of leaking StaticFiles' method response.
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            return response

        app.mount(
            "/",
            SpaStaticFiles(directory=resolved_dist, html=True),
            name="frontend",
        )

    return resolved_dist


def _is_api_path_used_as_spa_navigation(request: Request) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    if not _is_document_navigation(request.headers):
        return False

    path = request.url.path.rstrip("/") or "/"
    if path in SPA_NAVIGATION_PATHS:
        return True

    parent, separator, child = path.rpartition("/")
    return (
        separator == "/" and parent in {"/resumes", "/job-descriptions"} and bool(child)
    )


def _matches_non_frontend_route(app: FastAPI, scope: dict) -> bool:
    return any(
        route.name != "frontend" and route.matches(scope)[0] is not Match.NONE
        for route in app.routes
    )


def _is_document_navigation(headers: Headers) -> bool:
    content_type = headers.get("content-type", "").lower()
    if content_type and not content_type.startswith("text/html"):
        return False

    fetch_destination = headers.get("sec-fetch-dest")
    if fetch_destination:
        return (
            fetch_destination == "document"
            and headers.get("sec-fetch-mode") == "navigate"
        )
    return "text/html" in headers.get("accept", "")


def _mark_spa_entry(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Accept, Content-Type, Sec-Fetch-Dest, Sec-Fetch-Mode"
    return response
