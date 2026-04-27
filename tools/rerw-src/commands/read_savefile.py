"""read savefile — print field values from a Ravenswatch save file."""

from __future__ import annotations

from pathlib import Path

import click

from display_lib.output import error, info
from lib.save_edit import get_crc, read_field
from lib.save_fields import load_fields

NOT_PRESENT = "<not present>"


@click.command()
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Save file to read.",
)
@click.option(
    "--chapter",
    "want_chapter",
    is_flag=True,
    default=False,
    help="Print the chapter field only.",
)
@click.option(
    "--level",
    "want_level",
    is_flag=True,
    default=False,
    help="Print the level field only.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print sub-step detail (file size, CRC, per-GUID locations).",
)
def read_savefile_cmd(
    source: Path,
    want_chapter: bool,
    want_level: bool,
    verbose: bool,
) -> None:
    """Print field values from a save file.

    With no field flags, prints all registered fields. With one or more
    field flags, prints only those.
    """
    try:
        fields = load_fields()
    except Exception as exc:
        error(f"Failed to load save-field registry: {exc}")
        raise SystemExit(1) from exc

    try:
        data = source.read_bytes()
    except OSError as exc:
        error(f"Failed to read source: {exc}")
        raise SystemExit(1) from exc

    selected: list[str] = []
    if want_chapter:
        selected.append("chapter")
    if want_level:
        selected.append("level")
    if not selected:
        selected = list(fields.keys())

    # Validate the selection against the registry — defensive in case the
    # YAML drifts away from what the CLI flags expose.
    for name in selected:
        if name not in fields:
            error(f"Field '{name}' is not in the registry.")
            raise SystemExit(1)

    info(f"Source savefile: {source}")
    if verbose:
        info(f"  {len(data)} bytes, CRC=0x{get_crc(data):08X}")

    for name in selected:
        field = fields[name]
        value = read_field(data, field)
        if value is None:
            click.echo(f"{name}: {NOT_PRESENT}")
        else:
            click.echo(f"{name}: {value}")
