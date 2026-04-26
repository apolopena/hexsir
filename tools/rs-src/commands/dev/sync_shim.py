"""dev sync-shim — copy shim source from the repo to the deployed location."""

import shutil
from pathlib import Path

import click

from display_lib.output import error, info, success, warn

from lib import config
from lib.paths import shim_source_path, to_display_path


@click.command()
def sync_shim_cmd() -> None:
    """Copy rw/scripts/windows/rs_shim.py to $RS_SHIM_LOC.

    Pure local file copy — no shim RPC. Works regardless of attach state.
    The running shim still uses its old in-memory code; restart the shim on
    Windows to pick up the new file.
    """
    src = shim_source_path()
    dest = Path(config.shim_loc())

    if not src.exists():
        error(f"shim source not found at {src}")
        raise click.Abort()

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        error(f"could not create {dest.parent}: {e}")
        raise click.Abort()

    try:
        shutil.copyfile(src, dest)
    except OSError as e:
        error(f"copy failed: {e}")
        raise click.Abort()

    success(f"Synced rs_shim.py → {dest}")
    warn(
        "the running shim is still on the old code. "
        "restart it to pick up changes:"
    )
    info("  in your shim PowerShell, Ctrl+C and re-run:")
    info(f"      py {to_display_path(str(dest))}")
