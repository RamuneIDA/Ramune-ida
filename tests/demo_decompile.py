"""Demo: decompile functions through the full MCP chain with real IDA."""

import asyncio
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("IDADIR", "/home/explorer/ida-pro-9.3")
os.environ["PYTHONPATH"] = (
    "/home/explorer/ida-pro-9.3/idalib/python"
    + os.pathsep + os.environ.get("PYTHONPATH", "")
)

from ramune_ida.config import ServerConfig
import ramune_ida.server.app as app_module

BINARY = os.path.join(os.path.dirname(__file__), "binary", "client")


async def call(mcp, name, args=None):
    result = await mcp.call_tool(name, args or {})
    if isinstance(result, tuple):
        content_list = result[0]
    elif isinstance(result, list):
        content_list = result
    else:
        return result
    for item in content_list:
        text = getattr(item, "text", None)
        if text:
            return json.loads(text)


async def main():
    config = ServerConfig(
        worker_python=sys.executable,
        soft_limit=0, hard_limit=0, auto_save_interval=0,
        data_dir="/tmp/ramune-demo",
        output_max_length=5000,
    )
    app_module.configure(config)

    from ramune_ida.server.plugins import discover_tools, register_plugin_tools
    tools_meta = await discover_tools(sys.executable)
    register_plugin_tools(tools_meta)

    from ramune_ida.server.state import AppState
    state = AppState(config)
    await state.start()
    app_module._state = state
    mcp = app_module.mcp

    r = await call(mcp, "open_project", {"project_id": "demo"})
    work_dir = r["work_dir"]
    shutil.copy2(BINARY, os.path.join(work_dir, "client"))

    print("[*] Opening database...")
    r = await call(mcp, "open_database", {"project_id": "demo", "path": "client"})
    print(f"[+] status={r['status']}")

    funcs_to_try = ["main", "0x6D000"]
    for func in funcs_to_try:
        print(f"\n{'='*60}")
        print(f"DECOMPILE: {func}")
        print("=" * 60)
        r = await call(mcp, "decompile", {"project_id": "demo", "func": func})
        if "code" in r:
            code = r["code"]
            lines = code.split("\n")
            print(f"addr={r.get('addr')}, {len(lines)} lines")
            for line in lines[:20]:
                print(f"  {line}")
            if len(lines) > 20:
                print(f"  ... ({len(lines)} lines total)")
            print(f"\n  Output size: {len(code)} chars")
            if "truncated" in code:
                print("  *** TRUNCATED ***")
                print(f"  Last 200 chars: {code[-200:]}")
            print(f"\n  Full result keys: {list(r.keys())}")
        elif "error" in r:
            print(f"  ERROR: {r['error']}")
        else:
            print(f"  status={r.get('status')}")

    # Check truncated output files before cleanup
    print("\n" + "=" * 60)
    print("TRUNCATED OUTPUT FILES")
    print("=" * 60)
    work_dir = config.resolved_work_base_dir + "/demo"
    outputs_dir = os.path.join(work_dir, "outputs")
    if os.path.isdir(outputs_dir):
        for f in sorted(os.listdir(outputs_dir)):
            path = os.path.join(outputs_dir, f)
            size = os.path.getsize(path)
            print(f"  {f}: {size} bytes")
            with open(path) as fh:
                content = fh.read()
            print(f"    first 200 chars: {content[:200]}")
            print(f"    last 200 chars: {content[-200:]}")
    else:
        print("  No outputs directory found")

    # Test HTTP download via ASGI
    print("\n" + "=" * 60)
    print("HTTP DOWNLOAD TEST")
    print("=" * 60)
    import httpx
    http_app = app_module.mcp.streamable_http_app()
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for f in sorted(os.listdir(outputs_dir)) if os.path.isdir(outputs_dir) else []:
            url = f"/files/demo/outputs/{f}"
            resp = await client.get(url)
            print(f"  GET {url} -> {resp.status_code}, {len(resp.content)} bytes")

    await call(mcp, "close_database", {"project_id": "demo"})
    await call(mcp, "close_project", {"project_id": "demo"})
    await state.shutdown()
    app_module._state = None


if __name__ == "__main__":
    asyncio.run(main())
