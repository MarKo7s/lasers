"""Fixed log directory under ProgramData for TLB-8800 sessions."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from newfocus.tlb8800_utilities.idn import parse_idn

_LOG_ID_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_MODEL_DIR = "TLB8800"
_LOG_SUBPATH = Path("hardware") / "lasers" / _MODEL_DIR / "logs"


def program_data_lab_root() -> Path:
    """
    ``C:\\ProgramData\\LAB`` on Windows (via ``%PROGRAMDATA%``).

    Override with ``LAB_ROOT`` if set. On other OS, uses ``/var/lib/LAB``.
    """
    override = os.environ.get("LAB_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if sys.platform == "win32":
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(program_data) / "LAB"

    return Path("/var/lib/LAB")


def sanitize_log_id(raw: str) -> str:
    """Make a safe log file stem from an IDN string or serial."""
    text = raw.strip()
    if not text:
        return "unknown"
    cleaned = _LOG_ID_SAFE.sub("_", text).strip("._")
    return cleaned[:120] or "unknown"


def laser_id_from_idn(idn: str) -> str:
    """Derive log filename stem from a ``*IDN?`` / ``id?`` response."""
    parsed = parse_idn(idn)
    if parsed:
        for field in ("customer_serial", "nf_serial", "model"):
            value = parsed.get(field, "").strip()
            if value:
                return sanitize_log_id(value)
    return sanitize_log_id(idn)


def instrument_log_path(laser_id: str) -> Path:
    """
    ``<ProgramData>/LAB/hardware/lasers/TLB8800/logs/<laser_id>.log``

    Creates the directory tree if needed. Opens in append mode elsewhere — same
    file continues across sessions for the same instrument id.
    """
    stem = sanitize_log_id(laser_id)
    log_dir = program_data_lab_root() / _LOG_SUBPATH
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{stem}.log"


# Backward-compatible aliases
find_lab_root = program_data_lab_root
log_id_from_idn = laser_id_from_idn
