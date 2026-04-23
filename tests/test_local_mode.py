"""Tests for ``--local`` mode: cwd-bound projects, disabled /files
endpoints, absolute-path output URLs, and CLI flag interactions.

These tests intentionally avoid spawning a real worker; they exercise
the server-level machinery (state, output, HTTP endpoints, resources).
"""

from __future__ import annotations

import json
import logging
import os
import sys

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ramune_ida.config import ServerConfig
import ramune_ida.server.app as app_module
from ramune_ida.server.output import OutputStore
from ramune_ida.server.state import AppState


# ── Fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def local_state(tmp_path, monkeypatch):
    """AppState in local mode with cwd chdir'd to a tmp dir."""
    monkeypatch.chdir(tmp_path)

    config = ServerConfig(
        soft_limit=0,
        hard_limit=0,
        auto_save_interval=0,
        data_dir=str(tmp_path / "_data"),
        local_mode=True,
    )
    app_module.configure(config)

    state = AppState(config)
    await state.start()
    app_module._state = state
    yield state
    await state.shutdown()
    app_module._state = None


@pytest_asyncio.fixture
async def http_state(tmp_path):
    """AppState in default (non-local) mode for baseline comparison."""
    config = ServerConfig(
        soft_limit=0,
        hard_limit=0,
        auto_save_interval=0,
        data_dir=str(tmp_path),
        local_mode=False,
    )
    app_module.configure(config)

    state = AppState(config)
    await state.start()
    app_module._state = state
    yield state
    await state.shutdown()
    app_module._state = None


# ── ServerConfig ──────────────────────────────────────────────────


class TestServerConfigLocal:
    def test_default_false(self):
        cfg = ServerConfig()
        assert cfg.local_mode is False

    def test_opt_in(self):
        cfg = ServerConfig(local_mode=True)
        assert cfg.local_mode is True


# ── AppState behaviour ────────────────────────────────────────────


class TestAppStateLocal:
    @pytest.mark.asyncio
    async def test_start_skips_recovery(self, tmp_path, monkeypatch):
        """Local-mode start() must NOT scan cwd for 'projects'."""
        monkeypatch.chdir(tmp_path)
        fake_proj = tmp_path / "not-a-project"
        fake_proj.mkdir()

        cfg = ServerConfig(
            soft_limit=0, hard_limit=0, auto_save_interval=0,
            data_dir=str(tmp_path / "_data"), local_mode=True,
        )
        state = AppState(cfg)
        await state.start()
        try:
            assert "not-a-project" not in state.projects
        finally:
            await state.shutdown()

    @pytest.mark.asyncio
    async def test_open_project_maps_to_cwd(self, local_state, tmp_path):
        p1, _ = await local_state.open_project("alpha")
        p2, _ = await local_state.open_project("beta")
        assert p1.work_dir == str(tmp_path)
        assert p2.work_dir == str(tmp_path)
        # outputs are isolated per project
        assert p1.outputs_dir != p2.outputs_dir
        assert p1.outputs_dir.endswith(os.path.join(".ramune-outputs", "alpha"))
        assert p2.outputs_dir.endswith(os.path.join(".ramune-outputs", "beta"))

    @pytest.mark.asyncio
    async def test_close_project_preserves_cwd(self, local_state, tmp_path):
        user_file = tmp_path / "user_file.txt"
        user_file.write_text("don't touch me")

        p, _ = await local_state.open_project("gamma")
        os.makedirs(p.outputs_dir, exist_ok=True)
        sentinel = os.path.join(p.outputs_dir, "sentinel.json")
        with open(sentinel, "w") as f:
            f.write("{}")

        await local_state.close_project("gamma")

        # cwd and user file must survive
        assert tmp_path.is_dir()
        assert user_file.exists()
        assert user_file.read_text() == "don't touch me"
        # outputs_dir must be gone
        assert not os.path.isdir(p.outputs_dir)


# ── OutputStore URL form ──────────────────────────────────────────


class TestOutputStoreLocalURL:
    def test_local_url_is_absolute_path(self, local_state, tmp_path):
        store = OutputStore(max_length=10, preview_length=5)
        content = "x" * 500
        result, url = store.truncate_if_needed(
            content, "p", str(tmp_path / "outputs")
        )
        assert url is not None
        assert os.path.isabs(url)
        # the on-disk file actually exists
        assert os.path.isfile(url)
        assert url.endswith(".txt")

    def test_http_url_is_relative(self, http_state, tmp_path):
        store = OutputStore(max_length=10, preview_length=5)
        content = "x" * 500
        _, url = store.truncate_if_needed(
            content, "p", str(tmp_path / "outputs")
        )
        assert url is not None
        assert url.startswith("/files/p/outputs/")


# ── /files HTTP endpoints ─────────────────────────────────────────


class TestFilesEndpointsLocal:
    @pytest.mark.asyncio
    async def test_upload_disabled(self, local_state):
        await local_state.open_project("x")
        app = app_module.mcp.streamable_http_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.post(
                "/files/x",
                files={"file": ("a.bin", b"\x00", "application/octet-stream")},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_disabled(self, local_state, tmp_path):
        await local_state.open_project("x")
        app = app_module.mcp.streamable_http_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get("/files/x/anything.bin")
        assert resp.status_code == 404


# ── MCP resources ─────────────────────────────────────────────────


class TestResourcesLocal:
    @pytest.mark.asyncio
    async def test_project_files_disabled(self, local_state):
        from ramune_ida.server.resources import project_files

        await local_state.open_project("x")
        payload = json.loads(project_files("x"))
        # Should not reveal mode information to the AI.
        assert "mode" not in payload
        assert "error" in payload

    @pytest.mark.asyncio
    async def test_outputs_resource_uses_absolute_paths(
        self, local_state, tmp_path,
    ):
        from ramune_ida.server.resources import project_outputs

        p, _ = await local_state.open_project("x")
        # Seed one truncated output on disk (content must exceed
        # config.output_max_length to actually trigger truncation).
        max_len = local_state.output_store._max_length
        local_state.output_store.truncate_if_needed(
            "y" * (max_len + 100), "x", p.outputs_dir,
        )
        payload = json.loads(project_outputs("x"))
        assert payload["count"] == 1
        url = payload["outputs"][0]["download_url"]
        assert os.path.isabs(url)
        assert os.path.isfile(url)


# ── open_project tool return fields ───────────────────────────────


class TestOpenProjectToolLocal:
    @pytest.mark.asyncio
    async def test_local_returns_only_project_id(self, local_state):
        """Local mode must not leak server/mode details to the AI."""
        from ramune_ida.server.tools.session import open_project

        result = await open_project("alpha")
        assert result["project_id"] == "alpha"
        # No mode / work_dir / upload-download hints should surface.
        for forbidden in ("mode", "work_dir", "upload", "download", "curl_upload"):
            assert forbidden not in result, (
                f"{forbidden!r} should not appear in local open_project result"
            )

    @pytest.mark.asyncio
    async def test_local_reuse_still_notices(self, local_state):
        from ramune_ida.server.tools.session import open_project

        await open_project("alpha")
        result = await open_project("alpha")
        # Re-using an existing project id must still surface a notice.
        assert "already exists" in result.get("notice", "")
        for forbidden in ("mode", "work_dir", "upload"):
            assert forbidden not in result

    @pytest.mark.asyncio
    async def test_default_omits_local_fields(self, http_state):
        from ramune_ida.server.tools.session import open_project

        result = await open_project("alpha")
        assert "mode" not in result
        assert "work_dir" not in result
        # upload/download fields only appear when a request base URL is set,
        # which is never the case outside a real HTTP request.  We only
        # assert the local-only fields are absent.


# ── CLI ───────────────────────────────────────────────────────────


class TestCliLocal:
    def test_parse_stdio(self):
        from ramune_ida.cli import parse_transport_url
        t, h, p = parse_transport_url("stdio://")
        assert t == "stdio"
        assert h == ""
        assert p == 0

    def test_parse_stdio_ignores_extra(self):
        """stdio:// scheme shouldn't care about host/port content."""
        from ramune_ida.cli import parse_transport_url
        t, _, _ = parse_transport_url("stdio://irrelevant:1234")
        assert t == "stdio"

    def test_local_plus_web_disables_web(self, monkeypatch, caplog, tmp_path):
        """--local --web ... should warn and force args.web = False."""
        from ramune_ida import cli

        # Avoid actually starting a server.
        monkeypatch.setattr(
            cli, "_serve_stdio",
            lambda mcp: (_ for _ in ()).throw(SystemExit("stop")),
        )
        monkeypatch.setattr(
            cli, "_serve",
            lambda *a, **kw: (_ for _ in ()).throw(SystemExit("stop")),
        )

        # Run CLI with --local --web http://127.0.0.1:8000, expect warning
        # and SystemExit from our fake _serve.
        argv = ["ramune-ida", "--local", "--web", "stdio://"]
        monkeypatch.setattr(sys, "argv", argv)

        caplog.set_level(logging.WARNING, logger="ramune-ida.cli")
        with pytest.raises(SystemExit, match="stop"):
            cli.main()
        messages = " ".join(r.message for r in caplog.records)
        assert "local mode" in messages or "stdio transport" in messages

    def test_web_plus_stdio_disables_web(self, monkeypatch, caplog):
        """--web stdio:// without --local should also force web off."""
        from ramune_ida import cli

        monkeypatch.setattr(
            cli, "_serve_stdio",
            lambda mcp: (_ for _ in ()).throw(SystemExit("stop")),
        )
        argv = ["ramune-ida", "--web", "stdio://"]
        monkeypatch.setattr(sys, "argv", argv)

        caplog.set_level(logging.WARNING, logger="ramune-ida.cli")
        with pytest.raises(SystemExit, match="stop"):
            cli.main()
        messages = " ".join(r.message for r in caplog.records)
        assert "stdio transport" in messages
