"""Handlers for IDA database operations (open, close, save)."""

from __future__ import annotations

import logging
import os

import idapro

from ramune_ida.commands import CloseDatabase, OpenDatabase, SaveDatabase
from ramune_ida.protocol import ErrorCode, Method
from ramune_ida.worker.dispatch import handler, HandlerError

log = logging.getLogger(__name__)

_IDB_COMPONENT_EXTS = (".id0", ".id1", ".id2", ".nam", ".til")


def _find_residual_files(path: str) -> list[str]:
    """Return existing IDA component files for a given binary/IDB path."""
    stem = os.path.splitext(path)[0]
    return [stem + ext for ext in _IDB_COMPONENT_EXTS
            if os.path.isfile(stem + ext)]


def _remove_residual_files(path: str) -> list[str]:
    """Delete residual IDA component files, return removed paths."""
    removed = []
    for f in _find_residual_files(path):
        try:
            os.remove(f)
            removed.append(f)
        except OSError:
            pass
    return removed


@handler(Method.OPEN_DATABASE)
def handle_open_database(cmd: OpenDatabase) -> dict:
    if not cmd.path:
        raise HandlerError(ErrorCode.INVALID_PARAMS, "Missing required parameter: path")

    residuals = _find_residual_files(cmd.path)
    recovered = bool(residuals)

    rc = idapro.open_database(cmd.path, cmd.auto_analysis)

    if rc != 0 and residuals:
        log.warning(
            "open_database failed (rc=%d) with residual files, "
            "cleaning up and retrying from last saved state",
            rc,
        )
        _remove_residual_files(cmd.path)
        rc = idapro.open_database(cmd.path, cmd.auto_analysis)
        if rc == 0:
            import idc
            return {
                "path": cmd.path,
                "idb_path": idc.get_idb_path(),
                "recovered": True,
                "warning": "Recovery from component files failed. "
                           "Opened from last saved IDB — recent changes may be lost.",
            }

    if rc != 0:
        raise HandlerError(
            ErrorCode.DATABASE_OPEN_FAILED,
            f"open_database returned error code {rc} for {cmd.path}",
        )

    import idc
    idb_path = idc.get_idb_path()

    result: dict = {"path": cmd.path, "idb_path": idb_path}
    if recovered:
        result["recovered"] = True
    return result


@handler(Method.CLOSE_DATABASE)
def handle_close_database(cmd: CloseDatabase) -> dict:
    idapro.close_database(save=cmd.save)
    return {}


@handler(Method.SAVE_DATABASE)
def handle_save_database(cmd: SaveDatabase) -> dict:
    import ida_loader
    ida_loader.save_database("", 0)
    if cmd.idb_path:
        ida_loader.save_database(cmd.idb_path, 0)
    return {}
