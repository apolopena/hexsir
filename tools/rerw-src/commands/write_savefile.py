"""write savefile — edit field(s) and emit a CRC-correct save file."""

from __future__ import annotations

from pathlib import Path

import click

from display_lib.output import error, info, success
from lib.save_edit import get_crc, recompute_crc, write_field
from lib.save_fields import load_fields
from lib.skill_controllers import (
    SkillControllerError,
    load_hero_controllers,
    resolve_talent_id,
)
from lib.talent_edit import (
    TIER_VALUE_TO_NAME,
    TalentEditError,
    detect_hero,
    find_picks_anchor,
    find_talent_record,
    parse_tier,
    read_picks,
    write_pick,
    write_tier,
)

SAVE_FILENAME = "Profile_1.ob"
TALENT_FIELD = "run_picks"  # the hero-independent talent_picks field


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
    "--talent-slot",
    "talent_slot",
    type=click.IntRange(1, 5),
    default=None,
    help="Talent slot 1..5 to edit. Combine with --talent-id and/or --tier.",
)
@click.option(
    "--talent-id",
    "talent_id",
    type=str,
    default=None,
    help=(
        "New talent for --talent-slot N. Accepts a name/alias "
        "(e.g. 'Twin Dummies', 'Trait Twins') or a 32-hex-char GUID."
    ),
)
@click.option(
    "--tier",
    "tier_value",
    type=str,
    default=None,
    help=(
        "Tier for --talent-slot N. Accepts symbolic (Common/Rare/Epic/"
        "Legendary) or 0..3 numeric. Slots 1..4 only — slot 5 has no tier."
    ),
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
    talent_slot: int | None,
    talent_id: str | None,
    tier_value: str | None,
    force: bool,
    verbose: bool,
) -> None:
    """Edit field values, recompute CRC32, write Profile_1.ob into --dest.

    Each --chapter/--level flag locates registered GUID(s) and writes int32 LE.
    Talent edits use --talent-slot to pick the slot, then --talent-id (swap
    talent GUID), --tier (swap tier byte), or both (combined edit).
    Multiple flags edit atomically — one read, all writes, one CRC, one
    output file.
    """
    scalar_edits: list[tuple[str, int]] = []
    if chapter_value is not None:
        scalar_edits.append(("chapter", chapter_value))
    if level_value is not None:
        scalar_edits.append(("level", level_value))

    talent_edit_requested = (
        talent_slot is not None or talent_id is not None or tier_value is not None
    )
    if talent_edit_requested:
        if talent_slot is None:
            error("--talent-id / --tier require --talent-slot N to specify which slot.")
            raise SystemExit(2)
        if talent_id is None and tier_value is None:
            error("--talent-slot N requires --talent-id, --tier, or both.")
            raise SystemExit(2)
        if tier_value is not None and talent_slot == 5:
            error("Slot 5 (ult) has no tier; --tier is invalid for slot 5.")
            raise SystemExit(2)

    if not scalar_edits and not talent_edit_requested:
        error(
            "No edit flag supplied. Use --chapter, --level, "
            "or --talent-slot N with --talent-id / --tier."
        )
        raise SystemExit(2)

    if not dest.is_dir():
        error(f"Destination is not a directory: {dest}")
        raise SystemExit(1)

    try:
        fields = load_fields()
    except Exception as exc:
        error(f"Failed to load save-field registry: {exc}")
        raise SystemExit(1) from exc

    for name, _ in scalar_edits:
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

    summary: list[str] = []

    # Stage scalar edits first.
    for name, new_value in scalar_edits:
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
        old_value = located[0][2]
        summary.append(f"{name}: {old_value} -> {new_value}")
        if verbose:
            for guid, gpos, old in located:
                voff = gpos + 15
                click.echo(
                    f"  GUID {guid.hex()} located at 0x{gpos:x} -> "
                    f"writing int32 LE {new_value} at 0x{voff:x} (was {old})"
                )

    # Stage talent edits.
    if talent_edit_requested:
        if TALENT_FIELD not in fields:
            error(f"Talent field '{TALENT_FIELD}' is not in the registry.")
            raise SystemExit(1)
        talent_field = fields[TALENT_FIELD]
        if talent_field.type != "talent_picks":
            error(
                f"Field '{TALENT_FIELD}' has unexpected type "
                f"{talent_field.type!r}; expected 'talent_picks'."
            )
            raise SystemExit(1)
        try:
            hero = detect_hero(bytes(data))
        except TalentEditError as exc:
            error(str(exc))
            raise SystemExit(1) from exc
        skills_data_path = (
            f"{talent_field.extra['skills_data_dir']}/{hero.lower()}.yaml"
        )
        if verbose:
            info(f"Detected hero: {hero} -> {skills_data_path}")
        try:
            controllers = load_hero_controllers(skills_data_path)
        except SkillControllerError as exc:
            error(str(exc))
            raise SystemExit(1) from exc

        record_guid = talent_field.extra["record_guid"]
        sentinel = talent_field.extra["sentinel"]
        try:
            record_off = find_talent_record(data, record_guid)
            picks_start = find_picks_anchor(data, record_off, sentinel)
        except TalentEditError as exc:
            error(str(exc))
            raise SystemExit(1) from exc

        if verbose:
            info(
                f"Talent record body @ 0x{record_off:x}; "
                f"picks block @ 0x{picks_start:x}"
            )

        # Read current picks before any in-place writes — needed for the
        # tier-only path, since tier is read from the slot's CURRENT talent's
        # tag=0x10 record.
        current_picks = read_picks(data, picks_start, talent_field.extra["slot_count"])

        # 1. Talent-id swap (if requested).
        new_guid_for_tier: bytes
        if talent_id is not None:
            try:
                resolved = resolve_talent_id(controllers, talent_id)
            except SkillControllerError as exc:
                error(str(exc))
                raise SystemExit(1) from exc
            try:
                old_guid = write_pick(data, picks_start, talent_slot, resolved.guid)
            except TalentEditError as exc:
                error(str(exc))
                raise SystemExit(1) from exc
            new_guid_for_tier = resolved.guid
            summary.append(
                f"talent slot {talent_slot}: "
                f"{old_guid.hex()} -> {resolved.guid.hex()} ({resolved.name})"
            )
            if verbose:
                voff = picks_start + (talent_slot - 1) * 16
                click.echo(
                    f"  slot {talent_slot} GUID @ 0x{voff:x}: "
                    f"{old_guid.hex()} -> {resolved.guid.hex()}"
                )
        else:
            new_guid_for_tier = current_picks[talent_slot - 1]

        # 2. Tier swap (if requested) — write the tier byte to the tag=0x10
        # record matching the slot's NEW (or unchanged) talent.
        if tier_value is not None:
            try:
                tier_int = parse_tier(tier_value)
                old_tier = write_tier(data, new_guid_for_tier, tier_int)
            except TalentEditError as exc:
                error(str(exc))
                raise SystemExit(1) from exc
            old_tier_name = TIER_VALUE_TO_NAME.get(old_tier, f"u8={old_tier}")
            new_tier_name = TIER_VALUE_TO_NAME.get(tier_int, f"u8={tier_int}")
            summary.append(
                f"tier slot {talent_slot}: "
                f"{old_tier_name} ({old_tier}) -> {new_tier_name} ({tier_int})"
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

    for line in summary:
        click.echo(line)
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out}")
