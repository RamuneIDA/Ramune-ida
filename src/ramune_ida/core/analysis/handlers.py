"""Worker-side handlers for analysis tools.

Each function receives ``params: dict`` and returns ``dict``.
IDA modules are imported inside function bodies so the module
itself can be imported safely without IDA (e.g. during --list-plugins).

.. note:: Must stay compatible with Python 3.10.
   See :mod:`ramune_ida.worker` docstring for details.
"""

from __future__ import annotations

from typing import Any

from ramune_ida.core import ToolError


def _resolve_addr(func: str) -> int:
    """Resolve a function name or hex address string to an integer address."""
    import ida_name

    if func.startswith("0x") or func.startswith("0X"):
        try:
            return int(func, 16)
        except ValueError:
            pass

    try:
        return int(func)
    except ValueError:
        pass

    addr = ida_name.get_name_ea(0, func)
    if addr == 0xFFFFFFFFFFFFFFFF:  # BADADDR
        raise ToolError(-12, "Cannot resolve '%s'" % func)
    return addr


def decompile(params: dict[str, Any]) -> dict[str, Any]:
    """Decompile the function at *func* (name or hex address)."""
    import ida_funcs
    import ida_hexrays

    func_str = params.get("func", "")
    if not func_str:
        raise ToolError(-4, "Missing required parameter: func")

    addr = _resolve_addr(func_str)

    func_obj = ida_funcs.get_func(addr)
    if func_obj is None:
        raise ToolError(-12, "%s is not a function" % hex(addr))

    try:
        cfunc = ida_hexrays.decompile(func_obj.start_ea)
    except ida_hexrays.DecompilationFailure as exc:
        raise ToolError(-13, str(exc))

    if cfunc is None:
        raise ToolError(-13, "No result for %s" % hex(func_obj.start_ea))

    return {
        "addr": hex(func_obj.start_ea),
        "name": ida_funcs.get_func_name(func_obj.start_ea),
        "code": str(cfunc),
    }


def disasm(params: dict[str, Any]) -> dict[str, Any]:
    """Disassemble *count* instructions starting at *addr*."""
    import ida_ua
    import idc

    addr_str = params.get("addr", "")
    count = params.get("count", 20)

    if not addr_str:
        raise ToolError(-4, "Missing required parameter: addr")

    addr = _resolve_addr(addr_str)

    lines: list[dict[str, Any]] = []
    cur = addr
    for _ in range(count):
        insn = ida_ua.insn_t()
        length = ida_ua.decode_insn(insn, cur)
        if length == 0:
            break
        lines.append({
            "addr": hex(cur),
            "disasm": idc.GetDisasm(cur),
            "size": length,
        })
        cur += length

    return {"start_addr": hex(addr), "lines": lines}
