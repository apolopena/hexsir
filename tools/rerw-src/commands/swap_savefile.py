"""swap savefile — replace the active Profile_1.ob in the Ravenswatch install."""

import os
import shutil
from pathlib import Path

import click

from display_lib.output import error, info, success

DEFAULT_SAVEGAME_DIR = "/mnt/d/steam-storage/steamapps/common/Ravenswatch/_Save"
SAVE_FILENAME = "Profile_1.ob"


@click.command()
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Source save file to install (copied as Profile_1.ob).",
)
@click.option(
    "--dest",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Destination dir; overrides $RERW_SAVEGAME_DIR. "
    f"Default: {DEFAULT_SAVEGAME_DIR}",
)
def swap_savefile_cmd(source: Path, dest: Path | None) -> None:
    """Replace the active Profile_1.ob with a save file of your choosing.

    Reads the destination from $RERW_SAVEGAME_DIR (override with --dest);
    falls back to the default Ravenswatch install path. Always writes to
    Profile_1.ob — the game requires that exact filename. Overwrites any
    existing save without prompting; back up your current save first.
    """
    if dest is None:
        dest = Path(os.environ.get("RERW_SAVEGAME_DIR", DEFAULT_SAVEGAME_DIR))

    if not dest.is_dir():
        error(f"Destination is not a directory: {dest}")
        raise SystemExit(1)

    out = dest / SAVE_FILENAME
    info(f"{source} -> {out}")
    shutil.copy2(source, out)
    success(f"Wrote {out}")
