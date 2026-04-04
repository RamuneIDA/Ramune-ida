"""Listing API endpoints (functions, strings, imports, names)."""

from __future__ import annotations

from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ramune_ida.server.state import AppState
from ramune_ida.web.api.analysis import _execute_tool


def create_routes(get_state: Callable[[], AppState]) -> list[Route]:
    """Return Starlette Route objects for listing endpoints."""

    def _listing_params(request: Request) -> dict[str, Any]:
        params: dict[str, Any] = {}
        f = request.query_params.get("filter")
        if f:
            params["filter"] = f
        exclude = request.query_params.get("exclude")
        if exclude:
            params["exclude"] = exclude
        return params

    async def list_funcs(request: Request) -> JSONResponse:
        pid = request.path_params["pid"]
        return await _execute_tool(
            get_state, pid, "list_funcs", _listing_params(request), timeout=60.0,
        )

    async def list_strings(request: Request) -> JSONResponse:
        pid = request.path_params["pid"]
        return await _execute_tool(
            get_state, pid, "list_strings", _listing_params(request), timeout=60.0,
        )

    async def list_imports(request: Request) -> JSONResponse:
        pid = request.path_params["pid"]
        return await _execute_tool(
            get_state, pid, "list_imports", _listing_params(request), timeout=60.0,
        )

    async def list_names(request: Request) -> JSONResponse:
        pid = request.path_params["pid"]
        return await _execute_tool(
            get_state, pid, "list_names", _listing_params(request), timeout=60.0,
        )

    return [
        Route("/projects/{pid}/functions", list_funcs),
        Route("/projects/{pid}/strings", list_strings),
        Route("/projects/{pid}/imports", list_imports),
        Route("/projects/{pid}/names", list_names),
    ]
