"""mint savefile -- produce a clean starting save from a chapter-boss-kill proof.

Pure transformation — no semantic knobs. Output is always a chapter-1
starting save with every per-run field zeroed and every held-inventory
field zeroed (level=1, xp=0, stars=0, feathers=0, keys=0, etc.).
Customize the result after minting with `rerw write savefile`.
"""

from __future__ import annotations

from pathlib import Path

import click

from display_lib.output import error, info, success
from lib import cooked
from lib.save_edit import get_crc, recompute_crc, write_field
from lib.save_fields import load_fields
from lib.save_mint import mint_object_section
from lib.setters import FieldNotFound

SAVE_FILENAME = "Profile_1.ob"


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--source",
    required=True,
    envvar="RERW_SAVEFILE",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    metavar="<path>",
    help="Source savefile (a chapter-boss-kill proof). "
    "Defaults to $RERW_SAVEFILE if set.",
)
@click.option(
    "--dest",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    metavar="<dir>",
    help=f"Output directory; '{SAVE_FILENAME}' is written here.",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Overwrite existing dest file without prompting.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print sub-step detail.",
)
def mint_savefile_cmd(
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
) -> None:
    """Mint a clean starting save from a chapter-boss-kill proof.

    Output is always a chapter-1 starting save with every per-run field
    zeroed and every held-inventory field zeroed (level=1, xp=0, stars=0,
    feathers=0, keys=0, etc.). Customize after minting with
    `rerw write savefile`.
    """
    if not dest.is_dir():
        error(f"Destination is not a directory: {dest}")
        raise SystemExit(1)

    out_path = dest / SAVE_FILENAME
    if out_path.exists() and not force:
        error(f"Destination file exists (pass --force to overwrite): {out_path}")
        raise SystemExit(1)

    info(f"Source savefile: {source}")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        error(f"Failed to read source: {exc}")
        raise SystemExit(1) from exc

    try:
        cf = cooked.parse_file(raw)
    except Exception as exc:
        error(f"Failed to parse source as a cooked save: {exc}")
        raise SystemExit(1) from exc

    if verbose:
        info(f"  {len(raw)} bytes, CRC=0x{get_crc(raw):08X}, classes={len(cf.classes)}")

    try:
        report = mint_object_section(cf)
    except FieldNotFound as exc:
        error(f"Mint failed: {exc}")
        raise SystemExit(1) from exc

    minted_bytes = bytearray(cooked.encode_file(cf))

    # Chapter rollback to chapter 1 (= chapter index 0 in the file).
    try:
        fields = load_fields()
    except Exception as exc:
        error(f"Failed to load save-field registry: {exc}")
        raise SystemExit(1) from exc
    if "chapter" not in fields:
        error("Field 'chapter' is not in the registry; cannot roll chapter.")
        raise SystemExit(1)
    chapter_field = fields["chapter"]
    try:
        located = write_field(minted_bytes, chapter_field, 0)
    except ValueError as exc:
        error(f"Chapter rollback failed: {exc}")
        raise SystemExit(1) from exc
    final_crc = recompute_crc(minted_bytes)
    chapter_old = located[0][2]

    try:
        out_path.write_bytes(bytes(minted_bytes))
    except OSError as exc:
        error(f"Failed to write {out_path}: {exc}")
        raise SystemExit(1) from exc

    success(f"Wrote {out_path} ({len(minted_bytes)} bytes, CRC=0x{final_crc:08X})")
    info("Mint operations applied:")
    for step in report.steps:
        if verbose:
            click.echo(f"  - {step.label}: {step.old} -> {step.new}")
        else:
            click.echo(f"  - {step.label} -> {step.new}")
    if verbose:
        click.echo(
            f"  - chapter: {chapter_old} -> 0 (via {len(located)} GUID write(s))"
        )
    else:
        click.echo(f"  - chapter -> 0 (via {len(located)} GUID write(s))")
