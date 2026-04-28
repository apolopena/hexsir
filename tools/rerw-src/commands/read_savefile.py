"""read savefile — print field values from a Ravenswatch save file."""

from __future__ import annotations

from pathlib import Path

import click

from display_lib.output import error, info
from lib.save_edit import get_crc, read_field
from lib.save_fields import load_fields
from lib.skill_controllers import (
    SkillControllerError,
    load_hero_controllers,
)
from lib.talent_edit import (
    TIER_VALUE_TO_NAME,
    TalentEditError,
    detect_hero,
    find_picks_anchor,
    find_talent_record,
    read_picks,
    read_tier,
)

NOT_PRESENT = "<not present>"
TALENT_FIELD = "run_picks"


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
    "--talents",
    "want_talents",
    is_flag=True,
    default=False,
    help="Print the 5 talent picks and their tiers.",
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
    want_talents: bool,
    verbose: bool,
) -> None:
    """Print field values from a save file.

    With no field flags, prints all registered fields (including talents).
    With one or more flags, prints only those.
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

    explicit_flags = want_chapter or want_level or want_talents

    scalar_selected: list[str] = []
    if want_chapter:
        scalar_selected.append("chapter")
    if want_level:
        scalar_selected.append("level")
    if not explicit_flags:
        # Default: print all int32_le scalar fields plus talents.
        scalar_selected = [
            n for n, f in fields.items() if f.type == "int32_le"
        ]

    # Validate scalar selection against the registry.
    for name in scalar_selected:
        if name not in fields:
            error(f"Field '{name}' is not in the registry.")
            raise SystemExit(1)

    show_talents = want_talents or not explicit_flags

    info(f"Source savefile: {source}")
    if verbose:
        info(f"  {len(data)} bytes, CRC=0x{get_crc(data):08X}")

    # Print scalar fields first.
    for name in scalar_selected:
        field = fields[name]
        if field.type != "int32_le":
            continue
        value = read_field(data, field)
        if value is None:
            click.echo(f"{name}: {NOT_PRESENT}")
        else:
            click.echo(f"{name}: {value}")

    if not show_talents:
        return

    # Talents: locate record, read picks + per-pick tiers, format nicely.
    if TALENT_FIELD not in fields:
        if want_talents:
            error(f"Talent field '{TALENT_FIELD}' is not in the registry.")
            raise SystemExit(1)
        return
    talent_field = fields[TALENT_FIELD]
    if talent_field.type != "talent_picks":
        if want_talents:
            error(
                f"Field '{TALENT_FIELD}' has unexpected type "
                f"{talent_field.type!r}; expected 'talent_picks'."
            )
            raise SystemExit(1)
        return

    try:
        hero = detect_hero(data)
    except TalentEditError as exc:
        if want_talents:
            error(str(exc))
            raise SystemExit(1) from exc
        return

    skills_path = (
        f"{talent_field.extra['skills_data_dir']}/{hero.lower()}.yaml"
    )
    try:
        controllers = load_hero_controllers(skills_path)
    except SkillControllerError as exc:
        click.echo(f"talents: <hero {hero}: {exc}>")
        return

    # Build GUID -> SkillController for reverse lookup.
    by_guid = {c.guid: c for c in controllers.values()}

    try:
        record_off = find_talent_record(data, talent_field.extra["record_guid"])
        picks_start = find_picks_anchor(
            data, record_off, talent_field.extra["sentinel"]
        )
        picks = read_picks(
            data, picks_start, talent_field.extra["slot_count"]
        )
    except TalentEditError as exc:
        click.echo(f"talents: <{exc}>")
        return

    if verbose:
        info(
            f"Hero detected: {hero}; talent record body @ 0x{record_off:x}; "
            f"picks block @ 0x{picks_start:x}"
        )

    click.echo(f"talents: ({hero})")
    for i, guid in enumerate(picks, start=1):
        controller = by_guid.get(guid)
        canonical = (
            controller.name.replace("Skill Controller ", "")
            if controller
            else "<unknown controller>"
        )
        primary_alias = (
            controller.aliases[0]
            if controller and controller.aliases
            else None
        )
        display_name = (
            f"{primary_alias} ({canonical})"
            if primary_alias
            else canonical
        )
        try:
            tier_byte = read_tier(data, guid)
            tier_name = TIER_VALUE_TO_NAME.get(tier_byte, f"u8={tier_byte}")
            tier_str = f"{tier_name} (0x{tier_byte:02x})"
        except TalentEditError:
            tier_str = "<no tag=0x10 record found>"
        click.echo(f"  slot {i}: {display_name}  [tier: {tier_str}]")
