"""Project management API endpoints."""

from __future__ import annotations

import os
from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse

from ramune_ida.server.state import AppState


_NOT_READY = JSONResponse({"error": "Server starting up"}, status_code=503)


def _get_state_or_none(get_state: Callable[[], AppState]) -> AppState | None:
    try:
        return get_state()
    except RuntimeError:
        return None


def create_routes(get_state: Callable[[], AppState]) -> list:
    """Return Starlette Route objects for project management."""
    from starlette.routing import Route

    async def list_projects(request: Request) -> JSONResponse:
        state = _get_state_or_none(get_state)
        if state is None:
            return _NOT_READY
        projects = []
        for pid, project in state.projects.items():
            projects.append(_project_summary(pid, project))
        return JSONResponse({"projects": projects})

    async def get_project(request: Request) -> JSONResponse:
        state = _get_state_or_none(get_state)
        if state is None:
            return _NOT_READY
        pid = request.path_params["pid"]
        project = state.projects.get(pid)
        if project is None:
            return JSONResponse({"error": f"Unknown project: {pid}"}, status_code=404)
        return JSONResponse(_project_detail(pid, project))

    async def list_project_files(request: Request) -> JSONResponse:
        state = _get_state_or_none(get_state)
        if state is None:
            return _NOT_READY
        pid = request.path_params["pid"]
        project = state.projects.get(pid)
        if project is None:
            return JSONResponse({"error": f"Unknown project: {pid}"}, status_code=404)

        files: list[dict[str, Any]] = []
        if os.path.isdir(project.work_dir):
            for entry in os.scandir(project.work_dir):
                if entry.is_file():
                    stat = entry.stat()
                    files.append({
                        "name": entry.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })
        files.sort(key=lambda f: f["name"])
        return JSONResponse({"project_id": pid, "files": files})

    async def get_system(request: Request) -> JSONResponse:
        state = _get_state_or_none(get_state)
        if state is None:
            return _NOT_READY
        return JSONResponse({
            "instance_count": state.limiter.instance_count,
            "soft_limit": state.limiter._soft_limit,
            "hard_limit": state.limiter._hard_limit,
            "active_projects": list(state.limiter.active_projects),
            "project_count": len(state.projects),
        })

    async def open_database(request: Request) -> JSONResponse:
        state = _get_state_or_none(get_state)
        if state is None:
            return _NOT_READY
        pid = request.path_params["pid"]
        project = state.projects.get(pid)
        if project is None:
            return JSONResponse({"error": f"Unknown project: {pid}"}, status_code=404)

        body = await request.json()
        path = body.get("path", "")
        if not path:
            return JSONResponse({"error": "Missing 'path'"}, status_code=400)

        if not os.path.isabs(path):
            path = os.path.join(project.work_dir, path)
        path = os.path.realpath(path)

        if not os.path.isfile(path):
            return JSONResponse({"error": f"File not found: {path}"}, status_code=404)

        from ramune_ida.commands import Ping
        project.set_database(path)
        try:
            task = await project.execute(Ping(), timeout=300.0)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=500)

        return JSONResponse({
            "project_id": pid,
            "status": task.status.value,
            "idb_path": os.path.basename(project.idb_path) if project.idb_path else None,
            "exe_path": os.path.basename(project.exe_path) if project.exe_path else None,
        })

    async def close_database(request: Request) -> JSONResponse:
        state = _get_state_or_none(get_state)
        if state is None:
            return _NOT_READY
        pid = request.path_params["pid"]
        project = state.projects.get(pid)
        if project is None:
            return JSONResponse({"error": f"Unknown project: {pid}"}, status_code=404)

        if project._handle is None:
            return JSONResponse({"project_id": pid, "status": "no_worker"})

        from ramune_ida.commands import CloseDatabase as CloseDatabaseCmd
        import asyncio
        try:
            task = await asyncio.wait_for(
                project.execute(CloseDatabaseCmd()), timeout=30.0,
            )
            status = task.status.value
        except Exception:
            project.force_close()
            status = "killed"

        if project._handle is not None:
            project._handle.kill()
            project._handle = None
            project._limiter.on_destroyed(project.project_id)

        return JSONResponse({"project_id": pid, "status": status})

    return [
        Route("/projects", list_projects),
        Route("/projects/{pid}", get_project),
        Route("/projects/{pid}/files", list_project_files),
        Route("/projects/{pid}/open", open_database, methods=["POST"]),
        Route("/projects/{pid}/close", close_database, methods=["POST"]),
        Route("/system", get_system),
    ]


def _project_summary(pid: str, project: Any) -> dict[str, Any]:
    return {
        "project_id": pid,
        "has_database": project.has_database,
        "worker_alive": project._handle is not None and project._handle.is_alive(),
        "exe_path": os.path.basename(project.exe_path) if project.exe_path else None,
        "idb_path": os.path.basename(project.idb_path) if project.idb_path else None,
    }


def _project_detail(pid: str, project: Any) -> dict[str, Any]:
    detail = _project_summary(pid, project)
    detail["work_dir"] = project.work_dir
    detail["last_accessed"] = project.last_accessed
    detail["active_tasks"] = [
        t.to_dict() for t in project._tasks.values() if not t.is_done
    ]
    return detail
