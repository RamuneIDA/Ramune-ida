# Writing Plugins for Ramune-ida

Ramune-ida supports external plugins that add IDA analysis tools as MCP tools. Plugins are automatically discovered and registered — no source modification needed.

[中文版](writing-plugins_zh.md)

---

## Quick Start

Create a folder in `~/.ramune-ida/plugins/`:

```
~/.ramune-ida/plugins/
└── my_crypto/
    ├── __init__.py
    ├── metadata.py
    └── handlers.py
```

### 1. Define metadata

```python
# metadata.py

TOOLS = [
    {
        "name": "identify_crypto",
        "description": "Identify cryptographic algorithms by constant signatures (S-box, round constants).",
        "tags": ["crypto", "analysis"],
        "params": {
            "addr": {
                "type": "string",
                "required": False,
                "description": "Limit scan to a specific function address or name",
            },
        },
        "timeout": 120,
    },
]
```

### 2. Implement handlers

```python
# handlers.py

from ramune_ida.core import ToolError


def identify_crypto(params):
    import idaapi
    import ida_bytes

    addr = params.get("addr")
    # ... scan for crypto constants ...

    if not results:
        raise ToolError(-12, "No crypto patterns found")

    return {
        "algorithms": ["AES-128", "SHA-256"],
        "details": [
            {"name": "AES S-box", "addr": "0x4050A0", "confidence": 0.98},
        ],
    }
```

### 3. Export from package

```python
# __init__.py

from my_crypto.handlers import identify_crypto

__all__ = ["identify_crypto"]
```

Restart the server. The tool will appear in the MCP tool list automatically.

---

## Metadata Reference

Each entry in the `TOOLS` list:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | yes | Tool name, must be globally unique |
| `description` | str | yes | Shown to AI in MCP schema |
| `params` | dict | no | Parameter definitions (see below) |
| `tags` | list[str] | no | Category tags for future filtering |
| `timeout` | int | no | Default timeout in seconds (default: 30) |
| `handler` | str | no | Handler function name if different from `name` |

Each parameter entry:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | str | `"string"` | `"string"`, `"integer"`, `"number"`, `"boolean"` |
| `required` | bool | `True` | Whether the parameter is required |
| `default` | any | — | Default value for optional parameters |
| `description` | str | — | Shown to AI in MCP schema |

## Handler Contract

```python
def tool_name(params: dict[str, Any]) -> dict[str, Any]:
```

- **Input**: `params` dict with fields as defined in metadata
- **Output**: `dict` — merged into the MCP tool response
- **Errors**: raise `ToolError(code, message)` for structured error responses
- **IDA imports**: import inside the function body (the module is loaded during `--list-plugins` without idalib)
- **Cancellation**: handled automatically by the dispatch layer via `sys.setprofile`; no action needed in handler code
- **Python version**: must be compatible with the Worker's Python (>= 3.10)

## Plugin Directory

Default: `~/.ramune-ida/plugins/`

Override with the `RAMUNE_PLUGIN_DIR` environment variable or the `plugin_dir` config option.

The directory is scanned one level deep. Each sub-directory with a `metadata.py` is treated as a plugin package.

## Error Handling

Use `ToolError` for structured errors that should be returned to the AI:

```python
from ramune_ida.core import ToolError

def my_tool(params):
    addr = params.get("addr")
    if not addr:
        raise ToolError(-4, "Missing required parameter: addr")

    # ... work ...

    raise ToolError(-12, "Cannot resolve address")
```

Any other exception is caught by the dispatch layer and returned as an internal error.

## Testing

Test handlers directly without the MCP server:

```python
def test_identify_crypto():
    from my_crypto.handlers import identify_crypto
    # mock IDA modules as needed
    result = identify_crypto({"addr": "0x401000"})
    assert "algorithms" in result
```

For integration testing through the full MCP stack, see `tests/test_mcp_tools.py` in the ramune-ida repository.

## Name Conflicts

Tool names must be globally unique across all plugins and built-in tools. If a duplicate name is detected during discovery, the server will abort with an error message identifying both sources.

Use a namespace prefix for your tools: `crypto_identify` rather than `identify`.
