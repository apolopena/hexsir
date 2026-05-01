"""write savefile -- edit a single field of a savefile.

Group with one Click subcommand per editable field. Each subcommand
applies one named edit (single setter call), recomputes CRC, and writes
to --dest. Source is left untouched.

Object-section setters (feathers / stars / level / xp) flow:
  parse_file -> mutate cf.object_section via lib.setters -> encode_file -> write
Header-bytes setters (chapter / talent / tier) flow:
  read raw bytes -> mutate via GUID locators -> recompute_crc -> write

Backward compat: the parent command also accepts the legacy flags
(--chapter / --level / --talent-slot / --talent-id / --tier) with a
deprecation warning, forwarding to the subcommand logic. Will be
removed in a future release.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import click

from display_lib.output import error, info, success
from lib import cooked
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
from lib import setters

SAVE_FILENAME = "Profile_1.ob"
TALENT_FIELD = "run_picks"


# --- I/O option decorator (applied to every leaf subcommand) --------------


def _common_io_opts(f: Callable) -> Callable:
    """Attach the shared --source/--dest/-f/-v options to a subcommand."""
    f = click.option(
        "--verbose",
        "-v",
        is_flag=True,
        default=False,
        help="Print sub-step detail.",
    )(f)
    f = click.option(
        "--force",
        "-f",
        is_flag=True,
        default=False,
        help="Overwrite existing dest file without prompting.",
    )(f)
    f = click.option(
        "--dest",
        required=True,
        type=click.Path(file_okay=False, path_type=Path),
        metavar="<dir>",
        help=f"Output directory; '{SAVE_FILENAME}' is written here.",
    )(f)
    f = click.option(
        "--source",
        required=True,
        envvar="RERW_SAVEFILE",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        metavar="<path>",
        help="Source savefile. Defaults to $RERW_SAVEFILE if set.",
    )(f)
    return f


# --- Internal helpers -----------------------------------------------------


def _check_dest_writable(dest: Path, force: bool) -> Path:
    if not dest.is_dir():
        error(f"Destination is not a directory: {dest}")
        raise SystemExit(1)
    out_path = dest / SAVE_FILENAME
    if out_path.exists() and not force:
        error(f"Destination file exists (pass --force to overwrite): {out_path}")
        raise SystemExit(1)
    return out_path


def _apply_setter_edit(
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
    setter_fn: Callable[[cooked.CookedFile], int],
    field_label: str,
    new_value: int,
) -> None:
    """Common flow for object-section setter edits (feathers/stars/level/xp).

    Loads the source, applies setter_fn (which returns the old value) to
    the parsed CookedFile, encodes (auto-CRC), writes to dest. Output line
    is `field_label: <old> -> <new>`.
    """
    out_path = _check_dest_writable(dest, force)
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

    old_crc = get_crc(raw)
    if verbose:
        info(f"  {len(raw)} bytes, CRC=0x{old_crc:08X}, classes={len(cf.classes)}")

    try:
        old_value = setter_fn(cf)
    except (setters.FieldNotFound, ValueError) as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    encoded = cooked.encode_file(cf)
    new_crc = get_crc(encoded)
    try:
        out_path.write_bytes(encoded)
    except OSError as exc:
        error(f"Failed to write {out_path}: {exc}")
        raise SystemExit(1) from exc

    click.echo(f"{field_label}: {old_value} -> {new_value}")
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


def _apply_field_edit(
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
    field_name: str,
    new_value: int,
    field_label: str | None = None,
) -> None:
    """Common flow for GUID-locator scalar field edits (chapter only today).

    Operates on raw file bytes via lib.save_edit.write_field.
    """
    out_path = _check_dest_writable(dest, force)
    info(f"Source savefile: {source}")
    try:
        data = bytearray(source.read_bytes())
    except OSError as exc:
        error(f"Failed to read source: {exc}")
        raise SystemExit(1) from exc

    try:
        fields = load_fields()
    except Exception as exc:
        error(f"Failed to load save-field registry: {exc}")
        raise SystemExit(1) from exc
    if field_name not in fields:
        error(f"Field {field_name!r} is not in the registry.")
        raise SystemExit(1)
    field = fields[field_name]

    old_crc = get_crc(data)
    if verbose:
        info(f"  {len(data)} bytes, CRC=0x{old_crc:08X}")

    try:
        located = write_field(data, field, new_value)
    except ValueError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    old_value = located[0][2]
    new_crc = recompute_crc(data)
    try:
        out_path.write_bytes(bytes(data))
    except OSError as exc:
        error(f"Failed to write {out_path}: {exc}")
        raise SystemExit(1) from exc

    label = field_label or field_name
    click.echo(f"{label}: {old_value} -> {new_value}")
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


# --- Group with backward-compat shim --------------------------------------


@click.group(
    name="savefile",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--source", default=None, envvar="RERW_SAVEFILE", type=click.Path(path_type=Path))
@click.option("--dest", default=None, type=click.Path(path_type=Path))
@click.option("--chapter", "chapter_value", default=None, type=int)
@click.option("--level", "level_value", default=None, type=int)
@click.option("--talent-slot", "talent_slot", default=None, type=click.IntRange(1, 5))
@click.option("--talent-id", "talent_id", default=None, type=str)
@click.option("--tier", "tier_value", default=None, type=str)
@click.option("--force", "-f", "force", is_flag=True, default=False)
@click.option("--verbose", "-v", "verbose", is_flag=True, default=False)
@click.pass_context
def write_savefile_cmd(
    ctx: click.Context,
    source: Path | None,
    dest: Path | None,
    chapter_value: int | None,
    level_value: int | None,
    talent_slot: int | None,
    talent_id: str | None,
    tier_value: str | None,
    force: bool,
    verbose: bool,
) -> None:
    """Edit a single field of a savefile.

    Use a subcommand for each editable field, e.g.:

      rerw write savefile feathers 6 --source X --dest Y
      rerw write savefile chapter 1 --source X --dest Y
      rerw write savefile talent --slot 1 --key TraitTwins --source X --dest Y

    Run `rerw write savefile --help` to list all subcommands.
    """
    if ctx.invoked_subcommand is not None:
        return

    legacy_used = any(
        v is not None
        for v in [chapter_value, level_value, talent_slot, talent_id, tier_value]
    )
    if not legacy_used:
        if source is not None or dest is not None:
            error(
                "No field flag supplied. Use a subcommand: "
                "`rerw write savefile <field> <value>` "
                "(run `rerw write savefile --help` for the list)."
            )
            raise SystemExit(2)
        click.echo(ctx.get_help())
        return

    click.echo(
        "WARNING: top-level edit flags on `write savefile` are deprecated. "
        "Use `rerw write savefile <field> <value>` subcommands instead. "
        "(--chapter -> `chapter`, --level -> `level`, "
        "--talent-* -> `talent` / `tier`.) Will be removed in a future release.",
        err=True,
    )

    if source is None or dest is None:
        error("--source and --dest are required.")
        raise SystemExit(2)

    _legacy_atomic_edit(
        source,
        dest,
        chapter_value,
        level_value,
        talent_slot,
        talent_id,
        tier_value,
        force,
        verbose,
    )


def _legacy_atomic_edit(
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
    """Legacy atomic-multi-field edit path. Preserves the original
    write_savefile contract: one read, all writes, one CRC, one output.

    Output format matches the pre-refactor command exactly.
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
            "No field flag supplied. Use --chapter, --level, "
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

    if talent_edit_requested:
        if TALENT_FIELD not in fields:
            error(f"Talent field '{TALENT_FIELD}' is not in the registry.")
            raise SystemExit(1)
        talent_field = fields[TALENT_FIELD]
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

        current_picks = read_picks(
            data, picks_start, talent_field.extra["slot_count"]
        )

        new_guid_for_tier: bytes
        if talent_id is not None:
            try:
                resolved = resolve_talent_id(controllers, talent_id)
            except SkillControllerError as exc:
                error(str(exc))
                raise SystemExit(1) from exc
            try:
                old_guid = write_pick(
                    data, picks_start, talent_slot, resolved.guid
                )
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


# --- Subcommands: single-value scalars ------------------------------------


@write_savefile_cmd.command(
    name="chapter",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("value", type=click.IntRange(1, 4), metavar="<int 1..4>")
@_common_io_opts
def chapter_cmd(value: int, source: Path, dest: Path, force: bool, verbose: bool) -> None:
    """Set chapter. 1 = chapter 1, 4 = epilogue."""
    # User-facing 1..4 -> file-format 0..3.
    _apply_field_edit(source, dest, force, verbose, "chapter", value - 1, "chapter")


@write_savefile_cmd.command(
    name="feathers",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("count", type=click.IntRange(0), metavar="<int>")
@_common_io_opts
def feathers_cmd(count: int, source: Path, dest: Path, force: bool, verbose: bool) -> None:
    """Set the held Raven Feathers count.

    Spendable in-run on death — one feather per revive.
    """
    _apply_setter_edit(
        source,
        dest,
        force,
        verbose,
        lambda cf: setters.set_held_feathers(cf, count),
        "feathers (held)",
        count,
    )


@write_savefile_cmd.command(
    name="level",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("value", type=click.IntRange(1), metavar="<int 1..>")
@_common_io_opts
def level_cmd(value: int, source: Path, dest: Path, force: bool, verbose: bool) -> None:
    """Set the in-run hero level.

    NOTE: the per-run "Level reached" stat is computed as
      effective = level + xp / xp_threshold
    Set xp separately via `rerw write savefile xp`.
    """
    _apply_setter_edit(
        source,
        dest,
        force,
        verbose,
        lambda cf: setters.set_hero_level(cf, value),
        "level",
        value,
    )


@write_savefile_cmd.command(
    name="stars",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("count", type=click.IntRange(0), metavar="<int>")
@_common_io_opts
def stars_cmd(count: int, source: Path, dest: Path, force: bool, verbose: bool) -> None:
    """Set the Stars of Fate live spendable count (talent-reroll currency)."""
    _apply_setter_edit(
        source,
        dest,
        force,
        verbose,
        lambda cf: setters.set_stars(cf, count),
        "stars",
        count,
    )


@write_savefile_cmd.command(
    name="xp",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("value", type=click.IntRange(0), metavar="<int>")
@_common_io_opts
def xp_cmd(value: int, source: Path, dest: Path, force: bool, verbose: bool) -> None:
    """Set accumulated XP."""
    _apply_setter_edit(
        source,
        dest,
        force,
        verbose,
        lambda cf: setters.set_hero_xp(cf, value),
        "xp",
        value,
    )


# --- Subcommands: multi-value -------------------------------------------


@write_savefile_cmd.command(
    name="talent",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--slot",
    "-s",
    required=True,
    type=click.IntRange(1, 5),
    metavar="<int 1..5>",
    help="Slot to edit.",
)
@click.option(
    "--key",
    "-k",
    "key",
    required=True,
    type=str,
    metavar="<str>",
    help="Talent key. Run `rerw inspect game-assets` for valid keys.",
)
@click.option(
    "--tier",
    "-t",
    "tier",
    default=None,
    type=str,
    metavar="<0-3|common|rare|epic|legendary>",
    help="Optional; preserved if omitted.",
)
@_common_io_opts
def talent_cmd(
    slot: int,
    key: str,
    tier: str | None,
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
) -> None:
    """Set the talent in a slot."""
    if tier is not None and slot == 5:
        error("Slot 5 (ult) has no tier; --tier is invalid for slot 5.")
        raise SystemExit(2)
    out_path = _check_dest_writable(dest, force)
    info(f"Source savefile: {source}")
    try:
        data = bytearray(source.read_bytes())
    except OSError as exc:
        error(f"Failed to read source: {exc}")
        raise SystemExit(1) from exc
    try:
        fields = load_fields()
    except Exception as exc:
        error(f"Failed to load save-field registry: {exc}")
        raise SystemExit(1) from exc
    if TALENT_FIELD not in fields:
        error(f"Talent field {TALENT_FIELD!r} is not in the registry.")
        raise SystemExit(1)
    talent_field = fields[TALENT_FIELD]
    try:
        hero = detect_hero(bytes(data))
    except TalentEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
    skills_data_path = (
        f"{talent_field.extra['skills_data_dir']}/{hero.lower()}.yaml"
    )
    try:
        controllers = load_hero_controllers(skills_data_path)
    except SkillControllerError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
    try:
        resolved = resolve_talent_id(controllers, key)
    except SkillControllerError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
    try:
        record_off = find_talent_record(data, talent_field.extra["record_guid"])
        picks_start = find_picks_anchor(
            data, record_off, talent_field.extra["sentinel"]
        )
        old_guid = write_pick(data, picks_start, slot, resolved.guid)
    except TalentEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    summary = [
        f"talent slot {slot}: "
        f"{old_guid.hex()} -> {resolved.guid.hex()} ({resolved.name})"
    ]
    if tier is not None:
        try:
            tier_int = parse_tier(tier)
            old_tier = write_tier(data, resolved.guid, tier_int)
        except TalentEditError as exc:
            error(str(exc))
            raise SystemExit(1) from exc
        summary.append(
            f"tier slot {slot}: "
            f"{TIER_VALUE_TO_NAME.get(old_tier, old_tier)} -> "
            f"{TIER_VALUE_TO_NAME.get(tier_int, tier_int)}"
        )

    new_crc = recompute_crc(data)
    try:
        out_path.write_bytes(bytes(data))
    except OSError as exc:
        error(f"Failed to write {out_path}: {exc}")
        raise SystemExit(1) from exc
    for line in summary:
        click.echo(line)
    click.echo(f"CRC32: 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


@write_savefile_cmd.command(
    name="tier",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--slot",
    "-s",
    required=True,
    type=click.IntRange(1, 4),
    metavar="<int 1..4>",
    help="Slot. Slot 5 (ult) has no tier.",
)
@click.option(
    "--tier",
    "-t",
    "tier",
    required=True,
    type=str,
    metavar="<0-3|common|rare|epic|legendary>",
    help="Target tier.",
)
@_common_io_opts
def tier_cmd(
    slot: int,
    tier: str,
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
) -> None:
    """Set the tier of the talent currently in slot N."""
    out_path = _check_dest_writable(dest, force)
    info(f"Source savefile: {source}")
    try:
        data = bytearray(source.read_bytes())
    except OSError as exc:
        error(f"Failed to read source: {exc}")
        raise SystemExit(1) from exc
    try:
        fields = load_fields()
    except Exception as exc:
        error(f"Failed to load save-field registry: {exc}")
        raise SystemExit(1) from exc
    if TALENT_FIELD not in fields:
        error(f"Talent field {TALENT_FIELD!r} is not in the registry.")
        raise SystemExit(1)
    talent_field = fields[TALENT_FIELD]
    try:
        record_off = find_talent_record(data, talent_field.extra["record_guid"])
        picks_start = find_picks_anchor(
            data, record_off, talent_field.extra["sentinel"]
        )
        current_picks = read_picks(
            data, picks_start, talent_field.extra["slot_count"]
        )
        current_guid = current_picks[slot - 1]
        tier_int = parse_tier(tier)
        old_tier = write_tier(data, current_guid, tier_int)
    except TalentEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    new_crc = recompute_crc(data)
    try:
        out_path.write_bytes(bytes(data))
    except OSError as exc:
        error(f"Failed to write {out_path}: {exc}")
        raise SystemExit(1) from exc
    click.echo(
        f"tier slot {slot}: "
        f"{TIER_VALUE_TO_NAME.get(old_tier, old_tier)} -> "
        f"{TIER_VALUE_TO_NAME.get(tier_int, tier_int)}"
    )
    click.echo(f"CRC32: 0x{new_crc:08X}")
    success(f"Wrote {out_path}")
