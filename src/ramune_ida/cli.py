"""CLI entry point for ramune-ida.

Usage::

    ramune-ida                          # default http://127.0.0.1:8000
    ramune-ida http://0.0.0.0:8000     # Streamable HTTP
    ramune-ida sse://127.0.0.1:9000    # SSE (legacy)
    ramune-ida stdio://                 # stdio transport (MCP over stdin/stdout)
    ramune-ida --local stdio://         # local mode over stdio
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
from urllib.parse import urlparse


def parse_transport_url(url: str) -> tuple[str, str, int]:
    """Parse a transport URL into *(transport, host, port)*.

    Supported schemes: ``http`` / ``https`` (→ streamable-http),
    ``sse``, and ``stdio`` (host/port irrelevant).
    """
    parsed = urlparse(url)
    scheme = parsed.scheme or "http"

    if scheme == "stdio":
        return "stdio", "", 0

    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8000

    if scheme in ("http", "https"):
        transport = "streamable-http"
    elif scheme == "sse":
        transport = "sse"
    else:
        raise ValueError(f"Unsupported transport scheme: {scheme!r}")

    return transport, host, port


def main() -> None:
    from ramune_ida.config import DEFAULT_DATA_DIR, ENV_DATA_DIR

    env_data_dir = os.environ.get(ENV_DATA_DIR)

    parser = argparse.ArgumentParser(
        prog="ramune-ida",
        description="Headless IDA MCP Server",
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="http://127.0.0.1:8000",
        help="Transport URL: http://host:port, sse://host:port, stdio://",
    )
    parser.add_argument(
        "--soft-limit", type=int, default=4,
        help="Advisory threshold for open worker instances (default: 4)",
    )
    parser.add_argument(
        "--hard-limit", type=int, default=8,
        help="Maximum worker instances; 0 = unlimited (default: 8)",
    )
    parser.add_argument(
        "--worker-python", default="python",
        help="Python interpreter for Worker subprocesses (default: python)",
    )
    parser.add_argument(
        "--data-dir", default=env_data_dir or DEFAULT_DATA_DIR,
        help=(
            "Base directory for projects and plugins "
            f"(env: {ENV_DATA_DIR}, default: {DEFAULT_DATA_DIR})"
        ),
    )
    parser.add_argument(
        "--auto-save-interval", type=float, default=300.0,
        help="Seconds between auto-saves; 0 = disabled (default: 300)",
    )
    parser.add_argument(
        "--output-max-length", type=int, default=20_000,
        help="Truncate tool output beyond this many chars (default: 20000)",
    )
    parser.add_argument(
        "--exclude-tags", default="",
        help=(
            "Comma-separated tags to hide from MCP. "
            "Supports glob: core::*, name::execute_python, kind:unsafe"
        ),
    )
    parser.add_argument(
        "--web", action="store_true",
        help="Enable Web UI (served on the same port)",
    )
    parser.add_argument(
        "--local", action="store_true",
        help=(
            "Local mode: projects share the server cwd; file upload/download "
            "HTTP endpoints are disabled; large outputs are written to "
            "<cwd>/.ramune-outputs/<project_id>/ and referenced by absolute "
            "path. close_project does NOT delete the cwd."
        ),
    )

    args = parser.parse_args()

    import logging
    log = logging.getLogger("ramune-ida.cli")

    transport, host, port = parse_transport_url(args.url)

    if args.web and (args.local or transport == "stdio"):
        reason = "local mode" if args.local else "stdio transport"
        log.warning(
            "--web is disabled under %s (Web UI requires an HTTP server "
            "and, for local mode, would expose the cwd).",
            reason,
        )
        args.web = False

    from ramune_ida.config import ServerConfig
    from ramune_ida.server.app import configure, get_state, mcp

    exclude_tags = tuple(
        t.strip() for t in args.exclude_tags.split(",") if t.strip()
    )

    config = ServerConfig(
        worker_python=args.worker_python,
        soft_limit=args.soft_limit,
        hard_limit=args.hard_limit,
        auto_save_interval=args.auto_save_interval,
        data_dir=args.data_dir,
        output_max_length=args.output_max_length,
        exclude_tags=exclude_tags,
        local_mode=args.local,
    )
    configure(config)

    if transport == "stdio":
        asyncio.run(_serve_stdio(mcp))
        return

    from mcp.server.transport_security import TransportSecuritySettings

    mcp.settings.host = host
    mcp.settings.port = port

    if host in ("127.0.0.1", "localhost", "::1"):
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
        )
    else:
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )

    from starlette.types import ASGIApp, Receive, Scope, Send

    from ramune_ida.server.app import request_auth, request_base_url

    class _RequestCapture:
        """ASGI middleware that pins request-scoped headers into ContextVars.

        Captures:
          * ``Host`` → :data:`request_base_url`  (used to build upload/download URLs)
          * ``Authorization`` → :data:`request_auth`  (used by the per-tool ACL
            check; empty string when absent — i.e. trusted/legacy mode).
        """

        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            host = b""
            auth = b""
            for k, v in scope.get("headers", []):
                if k == b"host":
                    host = v
                elif k == b"authorization":
                    auth = v

            host_tok = (
                request_base_url.set(f"http://{host.decode()}") if host else None
            )
            auth_tok = request_auth.set(auth.decode()) if auth else None
            try:
                await self.app(scope, receive, send)
            finally:
                if auth_tok is not None:
                    request_auth.reset(auth_tok)
                if host_tok is not None:
                    request_base_url.reset(host_tok)

    if transport == "streamable-http":
        asgi_app = mcp.streamable_http_app()
    else:
        asgi_app = mcp.sse_app()

    if args.web:
        from ramune_ida.web.app import create_combined_app
        asgi_app = create_combined_app(
            mcp_app=asgi_app,
            get_state=get_state,
            dev_mode=bool(os.environ.get("RAMUNE_WEB_DEV")),
        )

    asyncio.run(_serve(
        _RequestCapture(asgi_app), host, port, mcp.settings.log_level.lower(),
    ))


async def _serve_stdio(mcp: object) -> None:
    """Run the FastMCP server over stdio with graceful shutdown."""
    # Install graceful shutdown for SIGINT/SIGTERM. FastMCP.run_stdio_async
    # will also catch KeyboardInterrupt, but we want AppState cleanup too.
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_event.set)
        except NotImplementedError:
            # Windows: fall back to default handlers.
            pass

    serve_task = asyncio.create_task(mcp.run_stdio_async())  # type: ignore[attr-defined]
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    try:
        await asyncio.wait(
            [serve_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        from ramune_ida.server import app as _app

        if _app._state is not None:
            await _app._state.shutdown()
            _app._state = None

        if not serve_task.done():
            serve_task.cancel()
            try:
                await serve_task
            except (asyncio.CancelledError, Exception):
                pass


async def _serve(app: object, host: str, port: int, log_level: str) -> None:
    """Run uvicorn with top-level signal handling for graceful shutdown."""
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_level=log_level)
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # we handle signals

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    serve_task = asyncio.create_task(server.serve())
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    await asyncio.wait(
        [serve_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    if shutdown_event.is_set():
        from ramune_ida.server import app as _app

        if _app._state is not None:
            await _app._state.shutdown()
            _app._state = None

        server.should_exit = True
        try:
            await asyncio.wait_for(serve_task, timeout=5.0)
        except asyncio.TimeoutError:
            serve_task.cancel()


if __name__ == "__main__":
    main()
