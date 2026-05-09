"""Tests for the lightweight per-project ACL based on the ``Authorization``
header.

The whole feature is implemented as:

  * a ContextVar (``request_auth``) populated from the inbound HTTP header
  * a ``.auth`` file under each project's work_dir recording the creator's
    auth string
  * a check inside ``register_tool``'s wrapper that rejects any tool call
    whose ``project_id`` is owned by a different auth
  * an ``open_project`` post-step that writes ``.auth`` for new projects
  * a filter inside the ``projects`` tool that hides projects owned by other
    auths

Trust mode (no Authorization header) keeps the legacy "see-all / do-all"
behaviour and is implicitly covered by the existing test suite.  This file
focuses on the new ACL paths only.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from typing import Any

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ramune_ida.config import ServerConfig
import ramune_ida.server.app as app_module
from ramune_ida.server.app import PROJECT_AUTH_FILE, request_auth


# ── Fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def mcp_app(tmp_path):
    """A FastMCP instance with session-level tools registered.

    We disable plugins so this fixture stays free of any IDA worker
    dependency — the ACL layer lives entirely above ``state`` and doesn't
    need a real worker to exercise.
    """
    config = ServerConfig(
        soft_limit=0,
        hard_limit=0,
        auto_save_interval=0,
        data_dir=str(tmp_path),
        plugins_enabled=False,
    )
    app_module.configure(config)

    from ramune_ida.server.state import AppState
    state = AppState(config)
    await state.start()
    app_module._state = state

    yield app_module.mcp

    await state.shutdown()
    app_module._state = None


# ── Helpers ───────────────────────────────────────────────────────


async def call(mcp, name: str, args: dict[str, Any] | None = None) -> dict:
    """Call an MCP tool and return the parsed dict result."""
    result = await mcp.call_tool(name, args or {})
    if isinstance(result, tuple):
        content_list = result[0]
    elif isinstance(result, list):
        content_list = result
    elif isinstance(result, dict):
        return result
    else:
        raise ValueError(f"Unexpected call_tool result: {type(result)}: {result}")
    for item in content_list:
        text = getattr(item, "text", None)
        if text:
            return json.loads(text)
    raise ValueError(f"No text content in call_tool result: {result}")


@contextlib.contextmanager
def as_auth(value: str):
    """Pin ``request_auth`` for the duration of the block."""
    tok = request_auth.set(value)
    try:
        yield
    finally:
        request_auth.reset(tok)


def auth_file_for(state, project_id: str) -> str:
    return os.path.join(state.projects[project_id].work_dir, PROJECT_AUTH_FILE)


# ── open_project: .auth stamping ──────────────────────────────────


@pytest.mark.asyncio
async def test_open_project_no_auth_does_not_stamp(mcp_app):
    state = app_module.get_state()

    r = await call(mcp_app, "open_project", {"project_id": "trust"})
    assert r["project_id"] == "trust"
    assert not os.path.exists(auth_file_for(state, "trust"))


@pytest.mark.asyncio
async def test_open_project_with_auth_stamps_file(mcp_app):
    state = app_module.get_state()
    with as_auth("alice-token"):
        await call(mcp_app, "open_project", {"project_id": "alice-foo"})

    path = auth_file_for(state, "alice-foo")
    assert os.path.isfile(path)
    with open(path) as f:
        assert f.read() == "alice-token"


@pytest.mark.asyncio
async def test_open_project_reuse_does_not_rewrite_auth(mcp_app, tmp_path):
    """Reuse of an existing project must not silently change ownership."""
    state = app_module.get_state()
    with as_auth("alice-token"):
        await call(mcp_app, "open_project", {"project_id": "alice-foo"})

    path = auth_file_for(state, "alice-foo")
    mtime_before = os.path.getmtime(path)

    # alice opens the same project again -> reuse path, .auth must remain
    # untouched.
    with as_auth("alice-token"):
        r = await call(mcp_app, "open_project", {"project_id": "alice-foo"})
    assert "notice" in r
    assert os.path.getmtime(path) == mtime_before


# ── ACL: cross-auth access is denied ──────────────────────────────


@pytest.mark.asyncio
async def test_other_auth_cannot_open_existing_project(mcp_app):
    with as_auth("alice-token"):
        await call(mcp_app, "open_project", {"project_id": "alice-foo"})

    with as_auth("bob-token"):
        with pytest.raises(Exception, match="already in use"):
            await call(mcp_app, "open_project", {"project_id": "alice-foo"})


@pytest.mark.asyncio
async def test_other_auth_cannot_close_project(mcp_app):
    with as_auth("alice-token"):
        await call(mcp_app, "open_project", {"project_id": "alice-foo"})

    with as_auth("bob-token"):
        with pytest.raises(Exception, match="already in use"):
            await call(mcp_app, "close_project", {"project_id": "alice-foo"})


@pytest.mark.asyncio
async def test_other_auth_cannot_invoke_arbitrary_tool(mcp_app):
    """The wrapper-level ACL should cover every tool that takes ``project_id``."""
    with as_auth("alice-token"):
        await call(mcp_app, "open_project", {"project_id": "alice-foo"})

    with as_auth("bob-token"):
        with pytest.raises(Exception, match="already in use"):
            await call(
                mcp_app,
                "get_task_result",
                {"project_id": "alice-foo", "task_id": "anything"},
            )


@pytest.mark.asyncio
async def test_unowned_project_is_open_to_anyone(mcp_app):
    """No ``.auth`` file ⇒ legacy/unowned ⇒ any auth may use it."""
    # create without auth — leaves no .auth file behind
    await call(mcp_app, "open_project", {"project_id": "legacy"})

    # alice can reuse it
    with as_auth("alice-token"):
        r = await call(mcp_app, "open_project", {"project_id": "legacy"})
    assert "notice" in r        # reuse path

    # bob can also reuse it
    with as_auth("bob-token"):
        r = await call(mcp_app, "open_project", {"project_id": "legacy"})
    assert "notice" in r


@pytest.mark.asyncio
async def test_owner_can_continue_to_use_their_project(mcp_app):
    with as_auth("alice-token"):
        await call(mcp_app, "open_project", {"project_id": "alice-foo"})
        # subsequent kwargs-style ACL-checked call from the same auth must pass
        r = await call(mcp_app, "close_project", {"project_id": "alice-foo"})
        assert r["status"] == "closed"


# ── projects: visibility filter ──────────────────────────────────


@pytest.mark.asyncio
async def test_projects_filter(mcp_app):
    # Set up:
    #   alice-foo  -> owned by alice
    #   bob-foo    -> owned by bob
    #   legacy     -> unowned
    with as_auth("alice-token"):
        await call(mcp_app, "open_project", {"project_id": "alice-foo"})
    with as_auth("bob-token"):
        await call(mcp_app, "open_project", {"project_id": "bob-foo"})
    await call(mcp_app, "open_project", {"project_id": "legacy"})

    # No auth -> sees everything (trust mode).
    r = await call(mcp_app, "projects")
    visible = {p["project_id"] for p in r["projects"]}
    assert visible == {"alice-foo", "bob-foo", "legacy"}

    # alice -> sees her own + unowned, NOT bob's.
    with as_auth("alice-token"):
        r = await call(mcp_app, "projects")
    visible = {p["project_id"] for p in r["projects"]}
    assert visible == {"alice-foo", "legacy"}

    # bob -> sees his own + unowned, NOT alice's.
    with as_auth("bob-token"):
        r = await call(mcp_app, "projects")
    visible = {p["project_id"] for p in r["projects"]}
    assert visible == {"bob-foo", "legacy"}


# ── local mode: ACL is a no-op ────────────────────────────────────


@pytest.mark.asyncio
async def test_local_mode_skips_auth_stamping(tmp_path):
    """In local mode every project shares the server cwd, so we never write
    ``.auth`` files even when a header would have been set."""
    config = ServerConfig(
        soft_limit=0,
        hard_limit=0,
        auto_save_interval=0,
        data_dir=str(tmp_path),
        plugins_enabled=False,
        local_mode=True,
    )
    app_module.configure(config)

    from ramune_ida.server.state import AppState
    state = AppState(config)
    await state.start()
    app_module._state = state
    try:
        with as_auth("alice-token"):
            await call(app_module.mcp, "open_project", {"project_id": "local-foo"})

        # No .auth anywhere — read_project_auth short-circuits in local mode.
        from ramune_ida.server.app import read_project_auth
        assert read_project_auth("local-foo") is None
    finally:
        await state.shutdown()
        app_module._state = None
