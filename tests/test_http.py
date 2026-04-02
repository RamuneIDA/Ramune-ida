"""HTTP transport and file endpoint tests.

Tests that the Starlette ASGI apps (streamable-http, SSE) can be
reached via httpx, and that file upload/download endpoints work
correctly including path traversal protection.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ramune_ida.config import ServerConfig
import ramune_ida.server.app as app_module


# ── Fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def state(tmp_path):
    """Start AppState, set module globals, yield, then shut down."""
    config = ServerConfig(
        soft_limit=0,
        hard_limit=0,
        auto_save_interval=0,
        data_dir=str(tmp_path),
    )
    app_module.configure(config)

    from ramune_ida.server.state import AppState
    s = AppState(config)
    await s.start()
    app_module._state = s
    yield s
    await s.shutdown()
    app_module._state = None


@pytest.fixture
def http_app(state):
    """Return the Streamable HTTP ASGI app."""
    return app_module.mcp.streamable_http_app()


@pytest.fixture
def sse_asgi(state):
    """Return the SSE ASGI app."""
    return app_module.mcp.sse_app()


@pytest_asyncio.fixture
async def project_with_file(state, tmp_path):
    """Create a project and put a file in its work_dir."""
    project, _ = await state.open_project("file-test")
    content = b"hello binary world"
    filepath = os.path.join(project.work_dir, "sample.bin")
    with open(filepath, "wb") as f:
        f.write(content)
    return project, content


# ── Transport availability ────────────────────────────────────────


@pytest.mark.asyncio
async def test_streamable_http_app_reachable(http_app):
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code in (200, 404, 405)


@pytest.mark.asyncio
async def test_sse_app_reachable(sse_asgi):
    transport = httpx.ASGITransport(app=sse_asgi)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code in (200, 404, 405)


# ── File upload ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_file(http_app, state):
    project, _ = await state.open_project("upload-test")
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/files/{project.project_id}",
            files={"file": ("test.bin", b"\xde\xad\xbe\xef", "application/octet-stream")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "test.bin"
    assert data["size"] == 4
    assert data["project_id"] == project.project_id
    assert os.path.isfile(os.path.join(project.work_dir, "test.bin"))


@pytest.mark.asyncio
async def test_upload_auto_creates_project(http_app, state):
    """Upload to a non-existent project auto-creates it."""
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/files/auto-created",
            files={"file": ("x.bin", b"\x00", "application/octet-stream")},
        )
    assert resp.status_code == 200
    assert "auto-created" in state.projects


@pytest.mark.asyncio
async def test_upload_missing_file_field(http_app, state):
    project, _ = await state.open_project("upload-nofield")
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/files/{project.project_id}",
            data={"notfile": "hello"},
        )
    assert resp.status_code == 400


# ── File download ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_file(http_app, project_with_file):
    project, content = project_with_file
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/files/{project.project_id}/sample.bin")
    assert resp.status_code == 200
    assert resp.content == content


@pytest.mark.asyncio
async def test_download_unknown_project(http_app):
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/files/nonexistent/file.bin")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_missing_file(http_app, state):
    project, _ = await state.open_project("dl-missing")
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/files/{project.project_id}/no-such-file.bin")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_path_traversal(http_app, project_with_file):
    project, _ = project_with_file
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/files/{project.project_id}/../../etc/passwd")
    assert resp.status_code in (403, 404)


# ── Upload then download roundtrip ────────────────────────────────


@pytest.mark.asyncio
async def test_upload_download_roundtrip(http_app, state):
    project, _ = await state.open_project("roundtrip")
    payload = os.urandom(1024)

    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/files/{project.project_id}",
            files={"file": ("data.bin", payload, "application/octet-stream")},
        )
        assert resp.status_code == 200

        resp = await client.get(f"/files/{project.project_id}/data.bin")
        assert resp.status_code == 200
        assert resp.content == payload


# ── Upload with subdirectory path ─────────────────────────────────


@pytest.mark.asyncio
async def test_download_nested_path(http_app, state):
    project, _ = await state.open_project("nested")
    subdir = os.path.join(project.work_dir, "outputs")
    os.makedirs(subdir)
    with open(os.path.join(subdir, "result.txt"), "w") as f:
        f.write("analysis result")

    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/files/{project.project_id}/outputs/result.txt")
    assert resp.status_code == 200
    assert resp.text == "analysis result"
