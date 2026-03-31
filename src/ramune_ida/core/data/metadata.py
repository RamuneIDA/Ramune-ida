"""Metadata for data reading tools (examine, get_bytes)."""

from __future__ import annotations

from ramune_ida.worker.tags import TAG_KIND_READ

TOOLS: list[dict] = [
    {
        "name": "examine",
        "description": "Examine an address. Auto-detects type (code, string, data, struct, unknown) and returns value.",
        "tags": ["data", TAG_KIND_READ],
        "params": {
            "addr": {
                "type": "string",
                "required": True,
                "description": "Address or name",
            },
            "size": {
                "type": "integer",
                "required": False,
                "default": 16,
                "description": "Bytes to read for unknown regions",
            },
        },
    },
    {
        "name": "get_bytes",
        "description": "Read raw bytes. Returns hex string.",
        "tags": ["data", TAG_KIND_READ],
        "params": {
            "addr": {
                "type": "string",
                "required": True,
            },
            "size": {
                "type": "integer",
                "required": True,
            },
        },
    },
]
