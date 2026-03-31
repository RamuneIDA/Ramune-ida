"""Metadata for undo tool."""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "undo",
        "description": "Undo recent modifications.",
        "tags": ["undo"],
        "params": {
            "count": {
                "type": "integer",
                "required": False,
                "default": 1,
            },
        },
    },
]
