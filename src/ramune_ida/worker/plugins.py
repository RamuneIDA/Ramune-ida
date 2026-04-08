"""Plugin discovery — scan built-in core package and external plugin folder.

All discovery logic lives here.  Both ``--list-plugins`` (metadata only)
and the normal Worker startup (metadata + handlers) call
:func:`discover_all`.

Sources (in order):
1. ``ramune_ida.core`` sub-packages (built-in, always scanned)
2. External plugin folder (``~/.ramune-ida/plugins`` by default,
   overridden by ``RAMUNE_PLUGIN_DIR`` env var)

.. note:: Must stay compatible with Python 3.10.
   See :mod:`ramune_ida.worker` docstring for details.
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import sys
from typing import Any, Callable

log = logging.getLogger(__name__)

ENV_PLUGIN_DIR = "RAMUNE_PLUGIN_DIR"
DEFAULT_PLUGIN_DIR = "~/.ramune-ida/plugins"
_CORE_PACKAGE = "ramune_ida.core"


def resolve_plugin_dir() -> str | None:
    """Return the resolved plugin directory, or *None* if it doesn't exist."""
    raw = os.environ.get(ENV_PLUGIN_DIR) or DEFAULT_PLUGIN_DIR
    path = os.path.expanduser(raw)
    return path if os.path.isdir(path) else None


def discover_all(plugin_dir: str | None = ...) -> tuple[list[dict[str, Any]], dict[str, Callable]]:  # type: ignore[assignment]
    """Discover tools from core package and (optionally) an external folder.

    Parameters
    ----------
    plugin_dir:
        Path to external plugin folder.  Pass ``None`` to skip folder
        scanning.  The default sentinel (``...``) triggers
        :func:`resolve_plugin_dir` automatically.
    """
    if plugin_dir is ...:
        plugin_dir = resolve_plugin_dir()

    all_tools: list[dict[str, Any]] = []
    handler_map: dict[str, Callable] = {}

    t, h = _scan_package(_CORE_PACKAGE)
    all_tools += t
    handler_map.update(h)

    if plugin_dir:
        t, h = _scan_folder(plugin_dir)
        all_tools += t
        handler_map.update(h)

    _check_duplicates(all_tools)
    return all_tools, handler_map


def _check_duplicates(tools: list[dict[str, Any]]) -> None:
    seen: dict[str, str] = {}
    for tool in tools:
        name = tool["name"]
        source = tool.get("_source", "?")
        if name in seen:
            raise RuntimeError(
                f"Duplicate tool name {name!r}: "
                f"first from {seen[name]!r}, again from {source!r}"
            )
        seen[name] = source


def _scan_package(package_name: str) -> tuple[list[dict[str, Any]], dict[str, Callable]]:
    """Scan an installed Python package for sub-packages with metadata + handlers."""
    tools: list[dict[str, Any]] = []
    handlers: dict[str, Callable] = {}

    try:
        package = importlib.import_module(package_name)
    except ImportError:
        log.warning("Cannot import package %s", package_name)
        return tools, handlers

    for _finder, sub_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if not is_pkg:
            continue
        sub_path = f"{package_name}.{sub_name}"
        t, h = _scan_submodule(sub_path, source=package_name)
        tools += t
        handlers.update(h)

    return tools, handlers


def _scan_folder(folder: str) -> tuple[list[dict[str, Any]], dict[str, Callable]]:
    """Scan a filesystem directory for plugin sub-directories."""
    tools: list[dict[str, Any]] = []
    handlers: dict[str, Callable] = {}

    if folder not in sys.path:
        sys.path.insert(0, folder)

    for entry in sorted(os.scandir(folder), key=lambda e: e.name):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        meta_path = os.path.join(entry.path, "metadata.py")
        if not os.path.isfile(meta_path):
            continue
        t, h = _scan_submodule(entry.name, source=folder)
        tools += t
        handlers.update(h)

    return tools, handlers


def _module_to_group(module_path: str) -> str:
    """Convert a Python module path to a plugin group prefix.

    Built-in:  ``ramune_ida.core.execution`` → ``core::execution``
    External:  ``my_plugin``                 → ``ext::my_plugin``
    """
    if module_path.startswith("ramune_ida."):
        return module_path[len("ramune_ida."):].replace(".", "::")
    return f"ext::{module_path.replace('.', '::')}"


def _scan_submodule(
    module_path: str,
    *,
    source: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Callable]]:
    """Import ``<module_path>.metadata`` for tool defs, then resolve
    handlers from the package itself (``from <module_path> import <fn>``).
    """
    tools: list[dict[str, Any]] = []
    handlers: dict[str, Callable] = {}

    try:
        meta_mod = importlib.import_module(f"{module_path}.metadata")
    except ImportError:
        return tools, handlers

    tools_list: list[dict[str, Any]] = getattr(meta_mod, "TOOLS", [])
    if not tools_list:
        return tools, handlers

    try:
        pkg = importlib.import_module(module_path)
    except ImportError:
        log.warning("Cannot import package %s", module_path)
        return tools, handlers

    group = _module_to_group(module_path)

    seen: set[str] = set()
    for tool in tools_list:
        name = tool["name"]
        if name in seen:
            continue
        fn_name = tool.get("handler", name)
        fn = getattr(pkg, fn_name, None)
        if fn is None:
            log.warning("Handler %r not exported by %s", fn_name, module_path)
            continue
        tool.setdefault("_source", source)
        tags = tool.setdefault("tags", [])
        tags.append(f"{group}::{name}")
        tags.append(f"name::{name}")
        tools.append(tool)
        handlers[name] = fn
        seen.add(name)

    return tools, handlers
