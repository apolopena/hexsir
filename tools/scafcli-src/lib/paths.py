"""Path resolution for scafcli.

All path logic lives here. Derived paths call get_root_dir() as their base.
"""

import os
import sys
from pathlib import Path

from display_lib.output import error


def get_root_dir() -> Path:
    """Get the project root directory from CLI_ROOT_DIR environment variable.

    In dev mode, the bash wrapper sets this automatically.
    For standalone CLIs, the user must export it.
    """
    root_dir = os.environ.get("CLI_ROOT_DIR")
    if not root_dir:
        error(
            "CLI_ROOT_DIR not set.\n"
            "  Export CLI_ROOT_DIR, or use the bash wrapper ./tools/scafcli if present."
        )
        sys.exit(1)
    root_path = Path(root_dir)
    if not root_path.is_dir():
        error(f"CLI_ROOT_DIR is not a valid directory: {root_dir}")
        sys.exit(1)
    return root_path


def get_scaf_data_dir() -> Path:
    """Return the bundled package data directory.

    Exception to the pathing standard for standalone tool support.
    uv tool install places package data beyond CLI_ROOT_DIR's reach, so we
    resolve from __file__. See coding-standards.md § Package-data paths.
    """
    return Path(__file__).resolve().parent.parent / "data"


def require_source_repo() -> Path:
    """Get source repo for scaffolding commands (repo, archive).

    Validates the scaffold manifest file exists.
    """
    root = get_root_dir()
    marker = root / "tools" / "scafcli-src" / "data" / "manifest.json"
    if not marker.exists():
        error("This command must run from the scaffold source repo")
        sys.exit(1)
    return root
