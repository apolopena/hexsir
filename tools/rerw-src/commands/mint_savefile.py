"""mint savefile -- produce a clean starting save from a chapter-boss-kill proof.

The mint takes an advanced chapter-N proof save, strips per-run accumulated
state, sets a Stars of Fate baseline, optionally rolls the chapter index
back to a chosen starting chapter, and emits a CRC-correct save file.

Per CLAUDE.md CLI rules: this is a transaction/apply command (batched edits)
and is therefore separate from `write savefile` (which holds single-field
edit primitives).
"""

from __future__ import annotations

from pathlib import Path

import click

from display_lib.output import error, info, success
from lib import cooked
from lib.save_edit import get_crc, write_field
from lib.save_fields import load_fields
from lib.save_mint import MintConfig, MintError, mint_object_section

SAVE_FILENAME = "Profile_1.ob"


@click.command()
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Source save file (a chapter-boss-kill proof).",
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
    type=click.IntRange(0, 3),
    default=0,
    show_default=True,
    help="Output chapter (0=ch1, 1=ch2, 2=ch3, 3=epilogue). Set to source chapter to skip rollback.",
)
@click.option(
    "--stars",
    "stars_value",
    type=click.IntRange(0),
    default=7,
    show_default=True,
    help="Stars of Fate baseline (live spendable count). Pass 0 to leave at proof value.",
)
@click.option(
    "--level",
    "level_value",
    type=click.IntRange(1),
    default=1,
    show_default=True,
    help="In-run hero level. XP is always reset to 0.",
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
    help="Print sub-step detail (each mint operation).",
)
def mint_savefile_cmd(
    source: Path,
    dest: Path,
    chapter_value: int,
    stars_value: int,
    level_value: int,
    force: bool,
    verbose: bool,
) -> None:
    """Mint a clean starting save from a chapter-boss-kill proof.

    Operations applied:
      - Zero per-run damage stats (HC body+0x11..+0x21)
      - Zero dream-shards-spent (HC body offset resolved dynamically;
        +0x35d in ch2 sources, +0x65d in ch3 sources, etc.)
      - Set Stars of Fate baseline (HC body+0x29 for empty-vec sources)
      - Remove ActivityScore records and zero parent's count u32
        (prevents chapter-N icon carryover on the score-details panel)
      - Zero HeroScoreData score floats (preserve counts and nickname)
      - Zero CurrentRunProfileData playtime
      - Set in-run hero level + XP=0
      - Roll chapter index to --chapter via registered GUID writes

    Works across chapters: HC body offsets that shift with content
    (notably dream-shards-spent) are resolved via lib.hc_walker.walk_hc_body
    instead of hardcoded values.
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

    config = MintConfig(
        stars_of_fate=stars_value if stars_value > 0 else None,
        hero_level=level_value,
        hero_xp=0,
    )

    try:
        report = mint_object_section(cf, config)
    except MintError as exc:
        error(f"Mint failed: {exc}")
        raise SystemExit(1) from exc

    # Re-encode (auto-recomputes body CRC32).
    minted_bytes = bytearray(cooked.encode_file(cf))

    # Chapter rollback uses the registered "chapter" field (GUID-based int32 LE write).
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
        located = write_field(minted_bytes, chapter_field, chapter_value)
    except ValueError as exc:
        error(f"Chapter rollback failed: {exc}")
        raise SystemExit(1) from exc
    # Re-encode again to recompute CRC over the new body bytes.
    # write_field edits raw header-prefixed bytes (not the cooked object section);
    # the body-CRC at offset 0x0C must be refreshed.
    from lib.save_edit import recompute_crc

    final_crc = recompute_crc(minted_bytes)
    chapter_old = located[0][2]
    chapter_msg = (
        f"chapter: {chapter_old} -> {chapter_value} "
        f"(via {len(located)} GUID write(s))"
    )

    out_path.write_bytes(bytes(minted_bytes))

    success(f"Wrote {out_path} ({len(minted_bytes)} bytes, CRC=0x{final_crc:08X})")
    info("Mint operations applied:")
    for step in report.steps:
        click.echo(f"  - {step}")
    click.echo(f"  - {chapter_msg}")
    if verbose:
        info(
            "Note: ActivityScore records are removed (count u32 zeroed) so the "
            "deserialize loop runs zero iterations. This sidesteps the silencer "
            "(no per-record deserialize -> no Error code 4) and prevents "
            "chapter-N icon carryover on the score-details panel. See "
            "rw/key-findings/save-silencer-mechanism.md for the silencer mechanism."
        )
