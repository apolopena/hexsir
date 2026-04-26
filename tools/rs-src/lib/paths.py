"""Path resolution for rs.

All path logic lives here. Derived paths call get_root_dir() as their base.
"""

import os
import re
import sys
from pathlib import Path

from display_lib.output import error


def to_display_path(path: str) -> str:
    """Convert WSL /mnt/<letter>/... paths to Windows-style for display.

    Used when printing instructions the user will paste into a Windows
    shell (PowerShell, cmd). Path-shape based; no platform detection. Any
    path that doesn't match the WSL pattern is returned unchanged, so the
    function is safe on native Windows or pure POSIX.
    """
    m = re.match(r"^/mnt/([a-z])/(.*)$", path, re.IGNORECASE)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace("/", "\\")
        return f"{drive}:\\{rest}"
    return path


def get_root_dir() -> Path:
    """Get the project root directory from CLI_ROOT_DIR environment variable.

    In dev mode, the bash wrapper sets this automatically.
    For standalone CLIs, the user must export it.
    """
    root_dir = os.environ.get("CLI_ROOT_DIR")
    if not root_dir:
        error(
            "CLI_ROOT_DIR not set.\n"
            "  Export CLI_ROOT_DIR, or use the bash wrapper ./tools/rs if present."
        )
        sys.exit(1)
    root_path = Path(root_dir)
    if not root_path.is_dir():
        error(f"CLI_ROOT_DIR is not a valid directory: {root_dir}")
        sys.exit(1)
    return root_path


def shim_source_path() -> Path:
    """Path to the shim source file in the repo (used by `dev sync-shim`)."""
    return get_root_dir() / "rw" / "scripts" / "windows" / "rs_shim.py"
