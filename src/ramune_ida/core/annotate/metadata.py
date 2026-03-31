"""Metadata for annotation tools (rename, comment)."""

from __future__ import annotations

from ramune_ida.worker.tags import TAG_KIND_READ, TAG_KIND_WRITE

TOOLS: list[dict] = [
    {
        "name": "rename",
        "description": (
            "Rename a symbol. "
            "Use addr for functions/globals, or func+var for local variables."
        ),
        "tags": ["annotate", TAG_KIND_WRITE],
        "params": {
            "addr": {
                "type": "string",
                "required": False,
                "description": "Target address or name",
            },
            "new_name": {
                "type": "string",
                "required": True,
            },
            "func": {
                "type": "string",
                "required": False,
                "description": "Containing function",
            },
            "var": {
                "type": "string",
                "required": False,
                "description": "Current variable name",
            },
        },
    },
    {
        "name": "get_comment",
        "description": (
            "Read comment. "
            "Use addr for disassembly line comment, or func for function header comment."
        ),
        "tags": ["annotate", TAG_KIND_READ],
        "params": {
            "addr": {
                "type": "string",
                "required": False,
                "description": "Address for disassembly line comment",
            },
            "func": {
                "type": "string",
                "required": False,
                "description": "Function address/name for header comment",
            },
        },
    },
    {
        "name": "set_comment",
        "description": (
            "Set comment. "
            "Use addr for disassembly line comment, or func for function header comment. "
            "Empty string clears the comment."
        ),
        "tags": ["annotate", TAG_KIND_WRITE],
        "params": {
            "addr": {
                "type": "string",
                "required": False,
                "description": "Address for disassembly line comment",
            },
            "func": {
                "type": "string",
                "required": False,
                "description": "Function address/name for header comment",
            },
            "comment": {
                "type": "string",
                "required": True,
            },
        },
    },
]
