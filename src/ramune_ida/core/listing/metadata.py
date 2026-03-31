"""Metadata for listing tools (list_funcs, list_strings, …)."""

from __future__ import annotations

from ramune_ida.worker.tags import TAG_KIND_READ

_PAGINATION_PARAMS: dict[str, dict] = {
    "filter": {
        "type": "string",
        "required": False,
        "description": "Substring filter",
    },
    "offset": {
        "type": "integer",
        "required": False,
        "default": 0,
    },
    "count": {
        "type": "integer",
        "required": False,
        "default": 100,
    },
}

TOOLS: list[dict] = [
    {
        "name": "list_funcs",
        "description": "List functions.",
        "tags": ["listing", TAG_KIND_READ],
        "params": {**_PAGINATION_PARAMS},
    },
    {
        "name": "list_strings",
        "description": "List strings found in the binary.",
        "tags": ["listing", TAG_KIND_READ],
        "params": {**_PAGINATION_PARAMS},
    },
    {
        "name": "list_imports",
        "description": "List imported functions.",
        "tags": ["listing", TAG_KIND_READ],
        "params": {**_PAGINATION_PARAMS},
    },
    {
        "name": "list_names",
        "description": "List all named addresses (functions, globals, labels).",
        "tags": ["listing", TAG_KIND_READ],
        "params": {**_PAGINATION_PARAMS},
    },
]
