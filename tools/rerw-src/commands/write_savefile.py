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
from lib import game_registry as registry
from lib.game_registry import RegistryError
from lib.hero_edit import HeroEditError, swap_hero
from lib.item_edit import (
    ItemEditError,
    add_item,
    remove_item,
    swap_item,
)
from lib.save_edit import get_crc, recompute_crc, write_field
from lib.save_fields import load_fields
from lib.skill_controllers import (
    SkillControllerError,
    load_hero_controllers,
    resolve_talent_id,
)
from lib.talent_edit import (
    RARITY_VALUE_TO_NAME,
    SLOT_COUNT,
    ULT_SLOT_INDEX,
    TalentEditError,
    clear_picks,
    detect_hero,
    find_picks_count,
    find_talent_record,
    parse_rarity,
    read_picks,
    write_all_rarity_bytes,
    write_all_slot_rarities,
    write_pick,
    write_rarity,
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
    setter_fn: Callable[[cooked.CookedFile], int | float],
    field_label: str,
    new_value: int | float,
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
@click.option(
    "--source",
    default=None,
    envvar="RERW_SAVEFILE",
    type=click.Path(path_type=Path),
    help="Source savefile (defaults to $RERW_SAVEFILE).",
)
@click.option(
    "--dest",
    default=None,
    type=click.Path(path_type=Path),
    help="Output directory.",
)
@click.option(
    "--chapter",
    "chapter_value",
    default=None,
    type=int,
    help="[DEPRECATED] Use `rerw write savefile chapter <int>` instead.",
)
@click.option(
    "--level",
    "level_value",
    default=None,
    type=int,
    help="[DEPRECATED] Use `rerw write savefile level <int>` instead.",
)
@click.option(
    "--talent-slot",
    "talent_slot",
    default=None,
    type=click.IntRange(1, 10),
    help="[DEPRECATED] Use `rerw write savefile talent --slot N --key X` instead.",
)
@click.option(
    "--talent-id",
    "talent_id",
    default=None,
    type=str,
    help="[DEPRECATED] Use `rerw write savefile talent --slot N --key X` instead.",
)
@click.option(
    "--rarity",
    "tier_value",
    default=None,
    type=str,
    help="[DEPRECATED] Use `rerw write savefile talent-rarity --slot N --rarity T` instead.",
)
@click.option(
    "--force",
    "-f",
    "force",
    is_flag=True,
    default=False,
    help="Overwrite existing dest file (used with deprecated flags).",
)
@click.option(
    "--verbose",
    "-v",
    "verbose",
    is_flag=True,
    default=False,
    help="Print sub-step detail (used with deprecated flags).",
)
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
        "--talent-* -> `talent` / `talent-rarity`.) Will be removed in a future release.",
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
            error("--talent-id / --rarity require --talent-slot N to specify which slot.")
            raise SystemExit(2)
        if talent_id is None and tier_value is None:
            error("--talent-slot N requires --talent-id, --rarity, or both.")
            raise SystemExit(2)
        if tier_value is not None and talent_slot == 5:
            error("Slot 5 (ult) has no rarity; --rarity is invalid for slot 5.")
            raise SystemExit(2)

    if not scalar_edits and not talent_edit_requested:
        error(
            "No field flag supplied. Use --chapter, --level, "
            "or --talent-slot N with --talent-id / --rarity."
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
        try:
            record_off = find_talent_record(data, record_guid)
            picks_count_off, picks_count = find_picks_count(data, record_off)
        except TalentEditError as exc:
            error(str(exc))
            raise SystemExit(1) from exc

        if verbose:
            info(
                f"Talent record body @ 0x{record_off:x}; "
                f"picks count u32 @ 0x{picks_count_off:x} (N={picks_count})"
            )

        current_picks = read_picks(data, picks_count_off, picks_count)

        new_guid_for_rarity: bytes
        if talent_id is not None:
            try:
                resolved = resolve_talent_id(controllers, talent_id)
            except SkillControllerError as exc:
                error(str(exc))
                raise SystemExit(1) from exc
            try:
                old_guid = write_pick(
                    data, picks_count_off, picks_count, talent_slot, resolved.guid
                )
            except TalentEditError as exc:
                error(str(exc))
                raise SystemExit(1) from exc
            new_guid_for_rarity = resolved.guid
            summary.append(
                f"talent slot {talent_slot}: "
                f"{old_guid.hex()} -> {resolved.guid.hex()} ({resolved.name})"
            )
            if verbose:
                voff = picks_count_off + 4 + (talent_slot - 1) * 16
                click.echo(
                    f"  slot {talent_slot} GUID @ 0x{voff:x}: "
                    f"{old_guid.hex()} -> {resolved.guid.hex()}"
                )
        else:
            new_guid_for_rarity = current_picks[talent_slot - 1]

        if tier_value is not None:
            try:
                rarity_int = parse_rarity(tier_value)
                old_rarity = write_rarity(data, new_guid_for_rarity, rarity_int)
            except TalentEditError as exc:
                error(str(exc))
                raise SystemExit(1) from exc
            old_rarity_name = RARITY_VALUE_TO_NAME.get(old_rarity, f"u8={old_rarity}")
            new_rarity_name = RARITY_VALUE_TO_NAME.get(rarity_int, f"u8={rarity_int}")
            summary.append(
                f"rarity slot {talent_slot}: "
                f"{old_rarity_name} ({old_rarity}) -> {new_rarity_name} ({rarity_int})"
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
    name="hero",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--key",
    "-k",
    "key",
    required=True,
    type=str,
    metavar="<str>",
    help="Strict hero key. Run `rerw game-assets inspect heroes` for valid keys.",
)
@_common_io_opts
def hero_cmd(
    key: str, source: Path, dest: Path, force: bool, verbose: bool
) -> None:
    """Swap the playable hero in the save.

    Rewrites the length-prefixed `Heroes\\<EngineName>.herodef.ot` reference
    inside the save body. Same-length swaps (e.g. Geppetto -> Carmilla,
    Geppetto -> Melusine) leave the file size unchanged; different-length
    swaps shift bytes after the hero record by the name-length delta. The
    engine tolerates shifts in the verified range -5 to +2 bytes.

    Resolves --key strictly against `data/heroes/*.yaml` (`hero.key`).
    Run `rerw game-assets inspect heroes` for the list of valid keys.
    """
    out_path = _check_dest_writable(dest, force)
    info(f"Source savefile: {source}")
    try:
        data = bytearray(source.read_bytes())
    except OSError as exc:
        error(f"Failed to read source: {exc}")
        raise SystemExit(1) from exc

    try:
        hero = registry.heroes().lookup(key)
    except RegistryError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    old_crc = get_crc(data)
    if verbose:
        info(f"  {len(data)} bytes, CRC=0x{old_crc:08X}")
        info(f"Target hero: key={hero.key} engine_name={hero.engine_name}")
        info(f"Target save_ref: {hero.save_ref}")

    try:
        old_engine_name, new_engine_name = swap_hero(data, hero.save_ref)
    except HeroEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    new_crc = recompute_crc(data)
    try:
        out_path.write_bytes(bytes(data))
    except OSError as exc:
        error(f"Failed to write {out_path}: {exc}")
        raise SystemExit(1) from exc

    click.echo(f"hero: {old_engine_name} -> {new_engine_name}")
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


@write_savefile_cmd.group(
    name="item",
    context_settings={"help_option_names": ["-h", "--help"]},
)
def item_grp() -> None:
    """Edit the magical-objects records array (swap / add / remove).

    The player's collected magical objects are stored as `tag=0x1a` records
    inside the run-state record. Each subcommand is a single edit:

      swap   --slot N --key X    replace slot N's runtime GUID
      add    --key X             append a new record at the end
      remove --slot N            drop the record at slot N

    Slot numbers are 1-indexed. Run `rerw read savefile` to inspect the
    current records (or `rerw game-assets inspect items` to discover keys).

    Engine validation: each save has a per-save record-count tolerance
    (Rule A fresh-ref cap, Rule C total-count ceiling). Adding too many
    records beyond the natural baseline can crash the engine on load.
    Use `add --reuse-counter-from-slot N` to bypass Rule A. See
    `rw/findings/magical-objects.md` for per-save tolerances.
    """


def _load_save_bytes(source: Path) -> bytearray:
    try:
        return bytearray(source.read_bytes())
    except OSError as exc:
        error(f"Failed to read source: {exc}")
        raise SystemExit(1) from exc


def _write_save_bytes(out_path: Path, data: bytes) -> None:
    try:
        out_path.write_bytes(data)
    except OSError as exc:
        error(f"Failed to write {out_path}: {exc}")
        raise SystemExit(1) from exc


@item_grp.command(
    name="swap",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--slot",
    "-s",
    required=True,
    type=click.IntRange(1),
    metavar="<int 1..>",
    help="Slot to overwrite (1-indexed).",
)
@click.option(
    "--key",
    "-k",
    "key",
    required=True,
    type=str,
    metavar="<str>",
    help="Strict item key. Run `rerw game-assets inspect items` for valid keys.",
)
@_common_io_opts
def item_swap_cmd(
    slot: int, key: str, source: Path, dest: Path, force: bool, verbose: bool
) -> None:
    """Replace slot N's runtime GUID with the keyed item's GUID.

    Constant-size edit; file size unchanged. Safe domain (per
    `rw/findings/magical-objects.md`): Legendary <-> Legendary or
    Cursed <-> Cursed swaps where neither item is in inventory. Swapping
    one of a stacked Common / Rare / Epic instance is unverified.
    """
    out_path = _check_dest_writable(dest, force)
    info(f"Source savefile: {source}")
    data = _load_save_bytes(source)

    try:
        item = registry.magical_items().lookup(key)
    except RegistryError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    old_crc = get_crc(data)
    if verbose:
        info(f"  {len(data)} bytes, CRC=0x{old_crc:08X}")
        info(f"Target item: key={item.key} display={item.display_name}")
        info(f"Target runtime GUID: {item.guid.hex()}")

    try:
        old_guid = swap_item(data, slot, item.guid)
    except ItemEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    new_crc = recompute_crc(data)
    _write_save_bytes(out_path, bytes(data))

    click.echo(
        f"item slot {slot}: {old_guid.hex()} -> "
        f"{item.guid.hex()} ({item.key})"
    )
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


@item_grp.command(
    name="add",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--key",
    "-k",
    "key",
    required=True,
    type=str,
    metavar="<str>",
    help="Strict item key. Run `rerw game-assets inspect items` for valid keys.",
)
@click.option(
    "--reuse-counter-from-slot",
    "reuse_slot",
    default=None,
    type=click.IntRange(1),
    metavar="<int 1..>",
    help=(
        "Copy the new record's counter from this existing slot to bypass "
        "the per-save Rule A fresh-reference cap. Default: last_counter+1 "
        "(uses a fresh reference)."
    ),
)
@_common_io_opts
def item_add_cmd(
    key: str,
    reuse_slot: int | None,
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
) -> None:
    """Append a new item record at the end of the records array.

    File size grows by 32 bytes. The new record's counter defaults to
    `last_counter + 1` (allocates a fresh reference); use
    `--reuse-counter-from-slot N` to copy from an existing slot and
    bypass the engine's Rule A fresh-reference cap.

    Engine ceilings vary per save (Rule C). See magical-objects.md for
    per-save tolerances.
    """
    out_path = _check_dest_writable(dest, force)
    info(f"Source savefile: {source}")
    data = _load_save_bytes(source)

    try:
        item = registry.magical_items().lookup(key)
    except RegistryError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    old_crc = get_crc(data)
    if verbose:
        info(f"  {len(data)} bytes, CRC=0x{old_crc:08X}")
        info(f"Target item: key={item.key} display={item.display_name}")
        if reuse_slot is not None:
            info(f"Reusing counter from slot {reuse_slot}")

    try:
        new_count = add_item(data, item.guid, reuse_counter_from_slot=reuse_slot)
    except ItemEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    new_crc = recompute_crc(data)
    _write_save_bytes(out_path, bytes(data))

    click.echo(f"item add: {item.key} -> slot {new_count} (count {new_count})")
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


@item_grp.command(
    name="remove",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--slot",
    "-s",
    required=True,
    type=click.IntRange(1),
    metavar="<int 1..>",
    help="Slot to remove (1-indexed).",
)
@_common_io_opts
def item_remove_cmd(
    slot: int, source: Path, dest: Path, force: bool, verbose: bool
) -> None:
    """Drop slot N's record from the records array.

    File size shrinks by 32 bytes. Slot indices of records after the
    removed slot decrease by one in subsequent calls.
    """
    out_path = _check_dest_writable(dest, force)
    info(f"Source savefile: {source}")
    data = _load_save_bytes(source)

    old_crc = get_crc(data)
    if verbose:
        info(f"  {len(data)} bytes, CRC=0x{old_crc:08X}")

    try:
        removed_guid = remove_item(data, slot)
    except ItemEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    new_crc = recompute_crc(data)
    _write_save_bytes(out_path, bytes(data))

    click.echo(f"item remove: slot {slot} (was runtime GUID {removed_guid.hex()})")
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


@write_savefile_cmd.command(
    name="keys",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("count", type=click.IntRange(0), metavar="<int>")
@_common_io_opts
def keys_cmd(count: int, source: Path, dest: Path, force: bool, verbose: bool) -> None:
    """Set the held Nightmare Keys count.

    Updates the existing Nightmare Keys record in the HeroIngredient vector.
    If the source has no keys record, `keys 0` is a no-op success; `keys N`
    (N > 0) errors because inserting a new record on an empty-vec save
    requires class-registry manipulation (deferred).
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
        old_value = setters.set_held_keys(cf, count)
    except NotImplementedError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
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

    click.echo(f"keys (held): {old_value} -> {count}")
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


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
    name="shards",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("count", type=click.FloatRange(0), metavar="<float>")
@_common_io_opts
def shards_cmd(count: float, source: Path, dest: Path, force: bool, verbose: bool) -> None:
    """Set the held Dream Shards count (HUD spendable currency).

    Stored as float32 at HC body+0x1D. Authoritative direct-read field —
    HUD shows this value verbatim and does not recompute it from
    earned − spent.
    """
    _apply_setter_edit(
        source,
        dest,
        force,
        verbose,
        lambda cf: setters.set_held_dream_shards(cf, count),
        "shards (held)",
        count,
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
    type=click.IntRange(1, 10),
    metavar="<int 1..10>",
    help="Slot to edit (1-10; save's actual count must include this slot).",
)
@click.option(
    "--key",
    "-k",
    "key",
    required=True,
    type=str,
    metavar="<str>",
    help="Strict talent key. Run "
    "`rerw game-assets inspect talents --for-hero <hero>` for valid keys.",
)
@click.option(
    "--rarity",
    "-r",
    "rarity",
    default=None,
    type=str,
    metavar="<common|rare|epic|legendary>",
    help="Optional; preserved if omitted. Lowercase only.",
)
@_common_io_opts
def talent_cmd(
    slot: int,
    key: str,
    rarity: str | None,
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
) -> None:
    """Set the talent in a slot.

    Resolves --key strictly against the hero's talent registry — exact match
    on `controllers[].key` only. No alias / display-name / GUID fallback.
    Run `rerw game-assets inspect talents --for-hero <key>` to discover
    valid talent keys.
    """
    if rarity is not None and slot == 5:
        error("Slot 5 (ult) has no rarity; --rarity is invalid for slot 5.")
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
        engine_name = detect_hero(bytes(data))
    except TalentEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
    try:
        hero = registry.heroes().lookup_by_engine_name(engine_name)
    except RegistryError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
    try:
        talent = registry.hero_talents(hero.key).lookup(key)
    except RegistryError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
    try:
        record_off = find_talent_record(data, talent_field.extra["record_guid"])
        picks_count_off, picks_count = find_picks_count(data, record_off)
        old_guid = write_pick(
            data, picks_count_off, picks_count, slot, talent.guid
        )
    except TalentEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    summary = [
        f"talent slot {slot}: "
        f"{old_guid.hex()} -> {talent.guid.hex()} ({talent.key})"
    ]
    if rarity is not None:
        try:
            rarity_int = parse_rarity(rarity)
            old_rarity = write_rarity(data, talent.guid, rarity_int)
        except TalentEditError as exc:
            error(str(exc))
            raise SystemExit(1) from exc
        summary.append(
            f"rarity slot {slot}: "
            f"{RARITY_VALUE_TO_NAME.get(old_rarity, old_rarity)} -> "
            f"{RARITY_VALUE_TO_NAME.get(rarity_int, rarity_int)}"
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
    name="talent-rarity",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--slot",
    "-s",
    required=True,
    type=click.IntRange(1, 10),
    metavar="<int 1..10 except 5>",
    help="Slot (1-10, except 5 — slot 5 is the ult and has no rarity).",
)
@click.option(
    "--rarity",
    "-r",
    "rarity",
    required=True,
    type=str,
    metavar="<common|rare|epic|legendary>",
    help="Target rarity (lowercase only).",
)
@_common_io_opts
def talent_rarity_cmd(
    slot: int,
    rarity: str,
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
) -> None:
    """Set the rarity of the talent currently in slot N."""
    if slot == 5:
        error("Slot 5 (ult) has no rarity.")
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
        record_off = find_talent_record(data, talent_field.extra["record_guid"])
        picks_count_off, picks_count = find_picks_count(data, record_off)
        if slot > picks_count:
            raise TalentEditError(
                f"slot {slot} not yet picked in this save (picks count = {picks_count})"
            )
        current_picks = read_picks(data, picks_count_off, picks_count)
        current_guid = current_picks[slot - 1]
        rarity_int = parse_rarity(rarity)
        old_rarity = write_rarity(data, current_guid, rarity_int)
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
        f"rarity slot {slot}: "
        f"{RARITY_VALUE_TO_NAME.get(old_rarity, old_rarity)} -> "
        f"{RARITY_VALUE_TO_NAME.get(rarity_int, rarity_int)}"
    )
    click.echo(f"CRC32: 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


@write_savefile_cmd.command(
    name="all-talent-rarities",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument(
    "rarity",
    type=str,
    metavar="<common|rare|epic|legendary>",
)
@_common_io_opts
def all_talent_rarities_cmd(
    rarity: str,
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
) -> None:
    """Bulk-set every talent's stored rarity in the hero's pool.

    Writes BOTH storage locations in one pass:
    1. The rarity byte on every tag=0x10 controller record (typically 28 per
       hero) — used by the picker when a slot has a valid loaded talent.
    2. The 10 per-slot u32 rarity entries in the tag=0x12 talent record —
       used by the picker when a slot's talent pointer is null (e.g. after
       a hero swap that invalidated the saved IDs).

    The ult slot (slot index 4 = user slot 5) is skipped in pass 2.
    Tag=0x10 records currently at the ult-marker sentinel (rarity=4) are
    skipped in pass 1. Every other slot/controller is written.

    Picker outcome: every proposal in the run displays the chosen rarity
    regardless of which talent gets stamped or whether the slot's saved
    talent is compatible with the active hero.
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
    if TALENT_FIELD not in fields:
        error(f"Talent field {TALENT_FIELD!r} is not in the registry.")
        raise SystemExit(1)
    talent_field = fields[TALENT_FIELD]
    try:
        rarity_int = parse_rarity(rarity)
        controllers_modified = write_all_rarity_bytes(data, rarity_int)
        slots_modified = write_all_slot_rarities(
            data, rarity_int, talent_field.extra["record_guid"]
        )
    except TalentEditError as exc:
        error(str(exc))
        raise SystemExit(1) from exc
    if controllers_modified == 0 and slots_modified == 0:
        error(
            "No records modified "
            "(save has no tag=0x10 records or all entries are ult-marker)."
        )
        raise SystemExit(1)

    new_crc = recompute_crc(data)
    try:
        out_path.write_bytes(bytes(data))
    except OSError as exc:
        error(f"Failed to write {out_path}: {exc}")
        raise SystemExit(1) from exc
    rarity_name = RARITY_VALUE_TO_NAME.get(rarity_int, rarity_int)
    click.echo(
        f"all-talent-rarities: {controllers_modified} controller rarity byte(s) "
        f"+ {slots_modified} per-slot rarity entry(ies) set to {rarity_name}"
    )
    click.echo(f"CRC32: 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


@write_savefile_cmd.command(
    name="clear-picks",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@_common_io_opts
def clear_picks_cmd(
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
) -> None:
    """Set picks count to 0 and delete the picks-block GUIDs.

    Produces the "all 10 slots empty" state. Combined with level=14, the
    engine fires picker invocations for all 10 HUD slots on level-up.
    Save shrinks by N×16 bytes where N was the prior picks count. CRC is
    recomputed automatically.

    Apply LAST in any edit chain — the destructive shrink invalidates the
    chapter-2 sentinel that older code paths use, but does not affect the
    new generalized picks-count locator.
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
    if TALENT_FIELD not in fields:
        error(f"Talent field {TALENT_FIELD!r} is not in the registry.")
        raise SystemExit(1)
    talent_field = fields[TALENT_FIELD]
    try:
        old_count = clear_picks(data, talent_field.extra["record_guid"])
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
        f"clear-picks: count {old_count} -> 0, deleted {old_count * 16} bytes"
    )
    click.echo(f"CRC32: 0x{new_crc:08X}")
    success(f"Wrote {out_path}")
