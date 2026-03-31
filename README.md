# Ramune-ida

> **[WIP] This project is under active development. APIs and features may change without notice.**

Headless IDA Pro MCP Server — expose IDA Pro's reverse engineering capabilities to AI agents via the [Model Context Protocol](https://modelcontextprotocol.io/).

[中文版](README_zh.md)

---

## What is this?

Ramune-ida runs IDA Pro (idalib) in headless mode and wraps it as an MCP server. AI agents like Claude, Cursor, or any MCP-compatible client can decompile functions, rename symbols, set types, and execute arbitrary IDAPython — all through structured tool calls.

## Key Design Decisions

**Process separation** — The MCP server and IDA run in separate processes. The server is pure async Python; each IDA worker is a single-threaded subprocess communicating via dedicated fd-pair pipes (JSON line protocol). This eliminates all thread-safety issues that plague IDA SDK usage.

**Plugin architecture** — Tools are defined by metadata (description, parameters, tags) and handler functions. The server discovers tools at startup, dynamically generates MCP tool functions, and dispatches calls to the worker. Adding a new tool requires only a metadata file and a handler — no boilerplate registration code. External plugins are supported via a plugin folder.

**Worker is stateless** — Workers are disposable command executors. All management state (task queues, crash recovery) lives in the Project layer. If a worker crashes, the project spawns a new one and reopens the IDB transparently.

## Architecture

```
MCP Client (Claude / Cursor / ...)
    │  Streamable HTTP / SSE
    ▼
┌──────────────────────────────────┐
│  MCP Server (async Python)       │
│  FastMCP + Project management    │
│  Plugin discovery + registration │
└──────────────┬───────────────────┘
               │  fd-pair pipe (JSON lines)
         ┌─────┼─────┐
         ▼     ▼     ▼
      Worker Worker Worker
      idalib idalib idalib
      (plugin handlers)
```

## Tools

### Session (7)

| Tool | Description |
|------|-------------|
| `open_project` | Create a new project workspace |
| `close_project` | Destroy a project and clean up |
| `projects` | List all open projects and their status |
| `open_database` | Open a binary or IDB in the project |
| `close_database` | Close the database and terminate IDA |
| `get_task_result` | Poll the result of a long-running task |
| `cancel_task` | Cancel a task |

### Analysis (4)

| Tool | Description |
|------|-------------|
| `decompile` | Decompile a function by name or address |
| `disasm` | Disassemble instructions at an address |
| `xrefs` | Get cross-references to an address |
| `survey` | Binary overview — file info, segments, functions, imports, strings |

### Annotation (3)

| Tool | Description |
|------|-------------|
| `rename` | Rename functions, globals, or local variables |
| `get_comment` | Read disassembly or function header comment |
| `set_comment` | Set disassembly or function header comment |

### Data (2)

| Tool | Description |
|------|-------------|
| `examine` | Auto-detect type at address (code, string, data, struct) |
| `get_bytes` | Read raw bytes as hex string |

### Listing (4)

| Tool | Description |
|------|-------------|
| `list_funcs` | List functions with filtering and pagination |
| `list_strings` | List strings found in the binary |
| `list_imports` | List imported functions |
| `list_names` | List all named addresses |

### Search (2)

| Tool | Description |
|------|-------------|
| `search` | Regex search across strings, names, types, disasm |
| `search_bytes` | Binary byte pattern search with wildcards |

### Type System (2)

| Tool | Description |
|------|-------------|
| `set_type` | Set type on functions, globals, or local variables |
| `define_type` | Declare C types (struct, enum, typedef, union) |

### Execution (1)

| Tool | Description |
|------|-------------|
| `execute_python` | Run arbitrary IDAPython with stdout/stderr capture |

### Undo (1)

| Tool | Description |
|------|-------------|
| `undo` | Undo recent modifications (IDA 9.0+ native undo) |

**Total: 26 tools** (19 plugin tools + 7 session tools)

## Infrastructure

- **Plugin architecture**: metadata-driven tool discovery, dynamic MCP registration, external plugin folder (`~/.ramune-ida/plugins/`)
- **Framework tags**: `kind:read` / `kind:write` / `kind:unsafe` — automatic undo points for write tools
- **Graceful cancellation**: SIGUSR1 + `sys.setprofile` hook → 5s watchdog → SIGKILL fallback
- **Output truncation**: oversized output truncated with HTTP download for full content
- **MCP Resources**: project and file discovery
- **File upload/download**: HTTP endpoints for binary and IDB transfer

## Plugins

Drop a plugin folder into `~/.ramune-ida/plugins/` (or set `RAMUNE_PLUGIN_DIR`) and restart. Tools appear automatically.

Each plugin is a Python package with `metadata.py` and `handlers.py`:

```
~/.ramune-ida/plugins/
└── my_plugin/
    ├── __init__.py     # from .handlers import my_tool
    ├── metadata.py     # TOOLS = [{"name": "my_tool", ...}]
    └── handlers.py     # def my_tool(params: dict) -> dict: ...
```

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
4. rename(project_id, addr="main", new_name="entry_main")
5. set_type(project_id, addr="0x401000", type="int foo(char *buf, int len)")
6. execute_python(project_id, code)        → run any IDAPython script
7. close_database(project_id)              → save and close
8. close_project(project_id)               → clean up
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
