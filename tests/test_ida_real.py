"""Real IDA integration tests — requires IDA Pro + idalib.

Run with: pytest tests/test_ida_real.py --run-ida

These tests spawn actual IDA Worker processes (no mock) and open
real binaries.  They verify the full pipeline from MCP tool call
through IPC to IDA API execution.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

IDA_DIR = os.environ.get("IDADIR", "/home/explorer/ida-pro-9.3")
IDA_PYTHON_PATH = os.path.join(IDA_DIR, "idalib", "python")
WORKER_PYTHON = sys.executable
BINARY_DIR = os.path.join(os.path.dirname(__file__), "binary")

pytestmark = pytest.mark.ida

# ── Setup ─────────────────────────────────────────────────────────

from ramune_ida.config import ServerConfig
import ramune_ida.server.app as app_module


_plugins_registered = False


@pytest_asyncio.fixture
async def mcp_ida(tmp_path):
    """Start MCP with real IDA worker (no mock)."""
    global _plugins_registered

    config = ServerConfig(
        worker_python=WORKER_PYTHON,
        soft_limit=0,
        hard_limit=2,
        auto_save_interval=0,
        data_dir=str(tmp_path),
    )

    os.environ["IDADIR"] = IDA_DIR
    os.environ["PYTHONPATH"] = IDA_PYTHON_PATH + os.pathsep + os.environ.get("PYTHONPATH", "")

    app_module.configure(config)

    if not _plugins_registered:
        from ramune_ida.server.plugins import discover_tools, register_plugin_tools
        tools_meta = await discover_tools(WORKER_PYTHON)
        register_plugin_tools(tools_meta)
        _plugins_registered = True

    from ramune_ida.server.state import AppState
    state = AppState(config)
    await state.start()
    app_module._state = state

    yield app_module.mcp

    await state.shutdown()
    app_module._state = None


async def call(mcp, name: str, args: dict | None = None) -> dict:
    result = await mcp.call_tool(name, args or {})
    if isinstance(result, tuple):
        content_list = result[0]
    elif isinstance(result, list):
        content_list = result
    elif isinstance(result, dict):
        return result
    else:
        raise ValueError(f"Unexpected: {type(result)}")
    for item in content_list:
        text = getattr(item, "text", None)
        if text:
            return json.loads(text)
    raise ValueError(f"No text content: {result}")


# ── Helpers ───────────────────────────────────────────────────────


def _copy_binary(name: str, work_dir: str) -> str:
    """Copy a test binary to the project work_dir."""
    src = os.path.join(BINARY_DIR, name)
    if not os.path.isfile(src):
        pytest.skip(f"Test binary not found: {src}")
    import shutil
    dest = os.path.join(work_dir, name)
    shutil.copy2(src, dest)
    return name


# ── Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_close_real_binary(mcp_ida):
    """Open a real binary, verify worker spawns, then close."""
    mcp = mcp_ida

    r = await call(mcp, "open_project", {"project_id": "ida-test"})
    pid = r["project_id"]
    binary = _copy_binary("ch01", r["work_dir"])

    r = await call(mcp, "open_database", {"project_id": pid, "path": binary})
    assert r["status"] == "completed"
    assert r.get("idb_path") is not None

    r = await call(mcp, "projects")
    p = r["projects"][0]
    assert p["has_worker"] is True
    assert p["has_database"] is True

    r = await call(mcp, "close_database", {"project_id": pid})
    assert r["status"] in ("completed", "killed")

    r = await call(mcp, "close_project", {"project_id": pid})
    assert r["status"] == "closed"


@pytest.mark.asyncio
async def test_reopen_idb(mcp_ida):
    """Open binary (creates IDB), close, reopen from IDB."""
    mcp = mcp_ida

    r = await call(mcp, "open_project", {"project_id": "reopen"})
    pid = r["project_id"]
    work_dir = r["work_dir"]
    binary = _copy_binary("ch01", work_dir)

    r = await call(mcp, "open_database", {"project_id": pid, "path": binary})
    assert r["status"] == "completed"
    idb_path = r.get("idb_path", "")

    r = await call(mcp, "close_database", {"project_id": pid})

    idb_name = os.path.basename(idb_path)
    if os.path.isfile(os.path.join(work_dir, idb_name)):
        r = await call(mcp, "open_database", {"project_id": pid, "path": idb_name})
        assert r["status"] == "completed"
        r = await call(mcp, "close_database", {"project_id": pid})

    await call(mcp, "close_project", {"project_id": pid})


@pytest.mark.asyncio
async def test_multiple_projects_real(mcp_ida):
    """Open two different binaries in separate projects."""
    mcp = mcp_ida

    r1 = await call(mcp, "open_project", {"project_id": "multi-a"})
    r2 = await call(mcp, "open_project", {"project_id": "multi-b"})

    bin_a = _copy_binary("ch01", r1["work_dir"])
    bin_b = _copy_binary("ch02", r2["work_dir"])

    ra = await call(mcp, "open_database", {"project_id": "multi-a", "path": bin_a})
    rb = await call(mcp, "open_database", {"project_id": "multi-b", "path": bin_b})
    assert ra["status"] == "completed"
    assert rb["status"] == "completed"

    r = await call(mcp, "projects")
    assert r["count"] == 2
    assert r["instance_count"] == 2

    await call(mcp, "close_database", {"project_id": "multi-a"})
    await call(mcp, "close_database", {"project_id": "multi-b"})
    await call(mcp, "close_project", {"project_id": "multi-a"})
    await call(mcp, "close_project", {"project_id": "multi-b"})


@pytest.mark.asyncio
async def test_decompile_via_mcp(mcp_ida):
    """Full MCP chain: open_project -> open_database -> decompile -> close."""
    mcp = mcp_ida

    r = await call(mcp, "open_project", {"project_id": "dec-real"})
    binary = _copy_binary("ch01", r["work_dir"])

    await call(mcp, "open_database", {"project_id": "dec-real", "path": binary})

    r = await call(mcp, "decompile", {"project_id": "dec-real", "func": "main"})
    assert r["status"] == "completed"
    assert "code" in r
    assert "addr" in r
    assert len(r["code"]) > 0

    await call(mcp, "close_database", {"project_id": "dec-real"})
    await call(mcp, "close_project", {"project_id": "dec-real"})
