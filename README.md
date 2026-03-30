# Ramune-ida

> **[WIP] This project is under active development. APIs and features may change without notice.**

Headless IDA Pro MCP Server — expose IDA Pro's reverse engineering capabilities to AI agents via the [Model Context Protocol](https://modelcontextprotocol.io/).

[中文版](README_zh.md)

---

## What is this?

Ramune-ida runs IDA Pro (idalib) in headless mode and wraps it as an MCP server. AI agents like Claude, Cursor, or any MCP-compatible client can decompile functions, trace cross-references, rename symbols, and execute arbitrary IDAPython — all through structured tool calls.

## Key Design Decisions

**Process separation** — The MCP server and IDA run in separate processes. The server is pure async Python; each IDA worker is a single-threaded subprocess communicating via dedicated fd-pair pipes (JSON line protocol). This eliminates all thread-safety issues that plague IDA SDK usage.

**Few thick tools, not many thin ones** — 14 core tools cover high-frequency operations with intelligent routing (e.g., `rename` handles globals, functions, and local variables). `execute_python` serves as a catch-all for anything the core tools don't cover.

**Worker is stateless** — Workers are disposable command executors. All management state (task queues, crash recovery) lives in the Project layer. If a worker crashes, the project spawns a new one and reopens the IDB transparently.

## Architecture

```
MCP Client (Claude / Cursor / ...)
    │  Streamable HTTP / SSE
    ▼
┌──────────────────────────────────┐
│  MCP Server (async Python)       │
│  FastMCP + Project management    │
└──────────────┬───────────────────┘
               │  fd-pair pipe (JSON lines)
         ┌─────┼─────┐
         ▼     ▼     ▼
      Worker Worker Worker
      idalib idalib idalib
```

## Current Status

### Implemented

Session tools (7):
`open_project`, `close_project`, `projects`, `open_database`, `close_database`, `get_task_result`, `cancel_task`

Analysis tools (2 MCP + 3 worker handlers):

| Tool | Status |
|------|--------|
| `decompile` | MCP + Worker |
| `execute_python` | MCP + Worker (stdout/stderr capture, `_result` convention, graceful cancel) |
| `disasm` | Worker handler only (MCP registration pending) |

Infrastructure:
- Graceful cancellation: SIGUSR1 + `sys.setprofile` hook → 5s watchdog → SIGKILL fallback
- Output truncation with HTTP download for full results
- MCP Resources for project/file discovery
- File upload/download via HTTP endpoints

### Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| Phase 0 | Session management refactor | Done |
| Phase 1 | Core analysis loop — decompile, disasm, xrefs, rename, survey, execute_python | In progress |
| Phase 2 | Query + search — list, search, read, resolve | Planned |
| Phase 3 | Annotation — set_type, define_type, set_comment, undo | Planned |
| Future | Plugin system, multi-agent collaboration | Design phase |

## Quick Start

### Requirements

- Python >= 3.10
- IDA Pro 9.0+ with idalib
- PDM (package manager)

### Install

```bash
git clone https://github.com/user/Ramune-ida.git
cd Ramune-ida
pdm install
```

### Run

```bash
# Default: Streamable HTTP on 127.0.0.1:8000
ramune-ida

# Specify host and port
ramune-ida http://0.0.0.0:8745

# Use IDA's bundled Python for workers
ramune-ida --worker-python /opt/ida/python3

# SSE transport (legacy MCP clients)
ramune-ida sse://127.0.0.1:9000
```

### MCP Client Configuration

For Claude Desktop or Cursor, add to your MCP config:

```json
{
  "mcpServers": {
    "ramune-ida": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### Basic Workflow

```
1. open_project()                          → get project_id
2. open_database(project_id, "target.exe") → IDA analyzes the binary
3. decompile(project_id, "main")           → decompiled C code
4. execute_python(project_id, code)        → run any IDAPython script
5. close_database(project_id)              → save and close
6. close_project(project_id)               → clean up
```

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `url` | `http://127.0.0.1:8000` | Transport URL |
| `--worker-python` | `python` | Python interpreter for IDA workers |
| `--soft-limit` | `4` | Advisory threshold for concurrent workers |
| `--hard-limit` | `8` | Maximum concurrent workers (0 = unlimited) |
| `--work-dir` | `~/.ramune-ida/projects` | Base directory for project files |
| `--auto-save-interval` | `300` | Seconds between auto-saves (0 = disabled) |
| `--output-max-length` | `50000` | Truncate tool output beyond this many chars |

## License

MIT

