"""Path resolution for hexsircli.

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
            "  Export CLI_ROOT_DIR, or use the bash wrapper ./tools/hexsircli if present."
        )
        sys.exit(1)
    root_path = Path(root_dir)
    if not root_path.is_dir():
        error(f"CLI_ROOT_DIR is not a valid directory: {root_dir}")
        sys.exit(1)
    return root_path
