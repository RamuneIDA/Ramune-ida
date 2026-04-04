"""Search API endpoints."""

from __future__ import annotations

from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ramune_ida.server.state import AppState
from ramune_ida.web.api.analysis import _execute_tool


def create_routes(get_state: Callable[[], AppState]) -> list[Route]:
    """Return Starlette Route objects for search endpoints."""

    async def search(request: Request) -> JSONResponse:
        pid = request.path_params["pid"]
        pattern = request.query_params.get("pattern")
        if not pattern:
            return JSONResponse({"error": "Missing 'pattern' param"}, status_code=400)
        params: dict[str, Any] = {"pattern": pattern}
        search_type = request.query_params.get("type")
        if search_type:
            params["type"] = search_type
        count = request.query_params.get("count")
        if count:
            params["count"] = int(count)
        return await _execute_tool(get_state, pid, "search", params)

    async def search_bytes(request: Request) -> JSONResponse:
        pid = request.path_params["pid"]
        pattern = request.query_params.get("pattern")
        if not pattern:
            return JSONResponse({"error": "Missing 'pattern' param"}, status_code=400)
        params: dict[str, Any] = {"pattern": pattern}
        count = request.query_params.get("count")
        if count:
            params["count"] = int(count)
        return await _execute_tool(get_state, pid, "search_bytes", params)

    return [
        Route("/projects/{pid}/search", search),
        Route("/projects/{pid}/search/bytes", search_bytes),
    ]
