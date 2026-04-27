"""write savefile — edit field(s) and emit a CRC-correct save file."""

from __future__ import annotations

from pathlib import Path

import click

from display_lib.output import error, info, success
from lib.save_edit import get_crc, recompute_crc, write_field
from lib.save_fields import load_fields

SAVE_FILENAME = "Profile_1.ob"


@click.command()
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Source save file to edit.",
)
@click.option(
    "--dest",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help=f"Destination directory; '{SAVE_FILENAME}' is written into it.",
)
@click.option(
    "--chapter",
    "chapter_value",
    type=int,
    default=None,
    help="Set chapter to N (0=ch1, 1=ch2, 2=ch3, 3=epilogue).",
)
@click.option(
    "--level",
    "level_value",
    type=int,
    default=None,
    help="Set in-run hero level to N.",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Overwrite an existing destination file without prompting.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print sub-step detail (file load, GUID locations, CRC before/after).",
)
def write_savefile_cmd(
    source: Path,
    dest: Path,
    chapter_value: int | None,
    level_value: int | None,
    force: bool,
    verbose: bool,
) -> None:
    """Edit field values, recompute CRC32, write Profile_1.ob into --dest.

    Each --chapter/--level flag locates the registered GUID(s), writes the
    new int32 LE value, and contributes to a single CRC recompute.
    Multiple flags edit atomically — one read, all writes, one CRC, one
    output file.
    """
    edits: list[tuple[str, int]] = []
    if chapter_value is not None:
        edits.append(("chapter", chapter_value))
    if level_value is not None:
        edits.append(("level", level_value))

    if not edits:
        error("No field flag supplied. Use --chapter N and/or --level N.")
        raise SystemExit(2)

    if not dest.is_dir():
        error(f"Destination is not a directory: {dest}")
        raise SystemExit(1)

    try:
        fields = load_fields()
    except Exception as exc:
        error(f"Failed to load save-field registry: {exc}")
        raise SystemExit(1) from exc

    for name, _ in edits:
        if name not in fields:
            error(f"Field '{name}' is not in the registry.")
            raise SystemExit(1)

    try:
        data = bytearray(source.read_bytes())
    except OSError as exc:
        error(f"Failed to read source: {exc}")
        raise SystemExit(1) from exc

    old_crc = get_crc(data)
    info(f"Source savefile: {source}")
    if verbose:
        info(f"  {len(data)} bytes, CRC=0x{old_crc:08X}")

    # Stage all edits, capturing old values, before the single CRC recompute.
    summary: list[tuple[str, int, int]] = []  # (name, old, new)
    for name, new_value in edits:
        field = fields[name]
        if verbose:
            info(
                f"Field: {name} (category={field.category}, "
                f"type={field.type}, guids={len(field.guids)})"
            )
        try:
            located = write_field(data, field, new_value)
        except ValueError as exc:
            error(str(exc))
            raise SystemExit(1) from exc

        # All parallel GUIDs hold the same value pre-edit; report the first.
        old_value = located[0][2]
        summary.append((name, old_value, new_value))

        if verbose:
            for guid, gpos, old in located:
                voff = gpos + 15
                click.echo(
                    f"  GUID {guid.hex()} located at 0x{gpos:x} -> "
                    f"writing int32 LE {new_value} at 0x{voff:x} (was {old})"
                )

    new_crc = recompute_crc(data)

    out = dest / SAVE_FILENAME
    if out.exists() and not force:
        if not click.confirm(f"{out} exists. Overwrite?", default=False):
            error("Aborted.")
            raise SystemExit(1)

    try:
        out.write_bytes(bytes(data))
    except OSError as exc:
        error(f"Failed to write {out}: {exc}")
        raise SystemExit(1) from exc

    for name, old_value, new_value in summary:
        click.echo(f"{name}: {old_value} -> {new_value}")
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out}")
