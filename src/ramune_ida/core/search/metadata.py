"""Metadata for search tools (search, search_bytes)."""

from __future__ import annotations

from ramune_ida.worker.tags import TAG_KIND_READ

TOOLS: list[dict] = [
    {
        "name": "search",
        "description": "Regex search across strings, names, types, and disasm. Specify type to narrow scope.",
        "tags": ["search", TAG_KIND_READ],
        "params": {
            "pattern": {
                "type": "string",
                "required": True,
                "description": "Python regex pattern",
            },
            "type": {
                "type": "string",
                "required": False,
                "default": "all",
                "description": "Scope: all, strings, names, types, disasm",
            },
            "count": {
                "type": "integer",
                "required": False,
                "default": 100,
            },
        },
    },
    {
        "name": "search_bytes",
        "description": "Binary byte pattern search with hex and ?? wildcards.",
        "tags": ["search", TAG_KIND_READ],
        "params": {
            "pattern": {
                "type": "string",
                "required": True,
                "description": "Hex bytes with ?? wildcards, e.g. '48 8B ?? 00'",
            },
            "count": {
                "type": "integer",
                "required": False,
                "default": 100,
            },
        },
    },
]
