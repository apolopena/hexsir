"""experimental — speculative save edits not yet promoted to stable.

Commands here may produce saves that fail to load. They exist to test
hypotheses about engine behavior. If a command reaches stable verified
behavior, it gets promoted into a real `write savefile` subcommand.
"""

from __future__ import annotations

import struct
from pathlib import Path

import click

from display_lib.output import error, info, success
from lib import cooked
from lib.cooked import MARK_END, MARK_START, ClassEntry
from lib.save_edit import get_crc

SAVE_FILENAME = "Profile_1.ob"

# Class entries cloned from a save that has GroupLevel records (e.g. the
# laser-lenses_1 chapter-2 proof). The parent class oCEntityCpntPersistentData
# must also be in the registry before GL can reference it by UID.
GL_PARENT_CLASS = ClassEntry(
    name="oCEntityCpntPersistentData",
    uid=0x0D51C9B9,
    version_major=1,
    version_minor=0,
    schema_version=1,
    parent_id=0x001DA16C,  # oISerializable, present in clean saves
)
GL_CLASS = ClassEntry(
    name="oCDtEntityCpntGroupLevelPersistentData",
    uid=0x190FE590,
    version_major=1,
    version_minor=0,
    schema_version=0,
    parent_id=0x0D51C9B9,
)
# Entity GUID lifted from a Geppetto chapter-2 save's GL record. May or may
# not be hero-independent — unknown. First test target is a Geppetto clean
# save, so this matches.
GL_ENTITY_GUID = bytes.fromhex("9e8fb5317efe6f4a95737325675793e6")


def _ensure_class(cf: cooked.CookedFile, entry: ClassEntry) -> int:
    for i, c in enumerate(cf.classes):
        if c.name == entry.name:
            return i
    cf.classes.append(entry)
    return len(cf.classes) - 1


def _build_gl_frame(class_index: int, level: int, xp: int) -> bytes:
    body = GL_ENTITY_GUID + b"\x00" + struct.pack("<II", level, xp)
    if len(body) != 25:
        raise RuntimeError(f"GL body should be 25 bytes, got {len(body)}")
    return (
        struct.pack("<II", MARK_START, class_index)
        + body
        + struct.pack("<I", MARK_END)
    )


def _insert_gl_into_section(
    cf: cooked.CookedFile, gl_class_idx: int, level: int, xp: int
) -> bytes:
    section = cf.object_section
    if len(section) < 8:
        raise ValueError("object section too short")
    if struct.unpack_from("<I", section, 0)[0] != MARK_START:
        raise ValueError("object section does not start with 0xAABB1111")
    table_count = struct.unpack_from("<I", section, 4)[0]
    table_end = 8 + table_count * 4
    if struct.unpack_from("<I", section, table_end)[0] != MARK_END:
        raise ValueError(f"expected 0xAABB2222 at 0x{table_end:x}")

    roots = cooked.parse_object_tree(cf)
    if table_count > len(roots):
        raise ValueError(
            f"parsed only {len(roots)} roots but instance table claims {table_count}"
        )
    end_of_in_table_roots = roots[table_count - 1].end

    new = bytearray(section)
    # 1. Append new entry (= GL class index) to instance table, before its
    #    closing 0xAABB2222 marker.
    new[table_end:table_end] = struct.pack("<I", gl_class_idx)
    # 2. Bump table count.
    struct.pack_into("<I", new, 4, table_count + 1)
    # 3. Insert GL frame at end of in-table roots region. The +4 compensates
    #    for the table insertion that shifted everything after table_end.
    insertion_point = end_of_in_table_roots + 4
    gl_frame = _build_gl_frame(gl_class_idx, level, xp)
    new[insertion_point:insertion_point] = gl_frame
    return bytes(new)


@click.group(
    name="experimental",
    context_settings={"help_option_names": ["-h", "--help"]},
)
def experimental_grp() -> None:
    """Experimental save edits — speculative; may produce broken saves."""


@experimental_grp.command(
    name="add-level-record",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--level",
    required=True,
    type=click.IntRange(1),
    metavar="<int>",
    help="Hero level to set in the new GL record.",
)
@click.option(
    "--xp",
    "xp_value",
    default=0,
    type=click.IntRange(0),
    metavar="<int>",
    help="Hero XP to set (default 0).",
)
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    metavar="<path>",
    help="Source savefile (typically a clean save with no GL record).",
)
@click.option(
    "--dest",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    metavar="<dir>",
    help=f"Output directory; '{SAVE_FILENAME}' is written here.",
)
@click.option("--force", "-f", is_flag=True, default=False)
@click.option("--verbose", "-v", is_flag=True, default=False)
def add_level_record_cmd(
    level: int,
    xp_value: int,
    source: Path,
    dest: Path,
    force: bool,
    verbose: bool,
) -> None:
    """EXPERIMENTAL: add a GroupLevelPersistentData record to a save lacking one.

    Adds the GL class (and parent oCEntityCpntPersistentData if missing) to
    the class registry, then inserts a new top-level GL record carrying the
    specified level/xp. Untested — the resulting save may fail to load or may
    behave unexpectedly. Targeted at clean saves where `rerw write savefile
    level` errors with 'expected exactly 1 instance of GroupLevel...'.
    """
    if not dest.is_dir():
        error(f"Destination is not a directory: {dest}")
        raise SystemExit(1)
    out_path = dest / SAVE_FILENAME
    if out_path.exists() and not force:
        error(f"Destination file exists (pass --force to overwrite): {out_path}")
        raise SystemExit(1)

    info(f"Source: {source}")
    raw = source.read_bytes()
    cf = cooked.parse_file(raw)
    old_crc = get_crc(raw)
    if verbose:
        info(f"  {len(raw)} bytes, CRC=0x{old_crc:08X}, classes={len(cf.classes)}")

    if any(c.name == GL_CLASS.name for c in cf.classes):
        error(
            f"Save already has {GL_CLASS.name} — use "
            f"`rerw write savefile level <int>` for stable edits."
        )
        raise SystemExit(1)

    parent_idx = _ensure_class(cf, GL_PARENT_CLASS)
    gl_idx = _ensure_class(cf, GL_CLASS)
    if verbose:
        info(f"  parent class -> registry index {parent_idx}")
        info(f"  GL class     -> registry index {gl_idx}")

    cf.object_section = _insert_gl_into_section(cf, gl_idx, level, xp_value)

    encoded = cooked.encode_file(cf)
    new_crc = get_crc(encoded)
    out_path.write_bytes(encoded)

    click.echo(
        f"experimental add-level-record: level={level} xp={xp_value} "
        f"(GL class index {gl_idx}, parent index {parent_idx})"
    )
    click.echo(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    success(f"Wrote {out_path}")


# ===========================================================================
# find-talent-seeds — offline brute-force seed solver
# ===========================================================================
import re

import yaml

from lib.picker_seed_solver import MASK31, find_seeds, simulate

HEROES_DIR = Path(__file__).resolve().parents[1] / "data" / "heroes"


def _load_hero_talents(hero_key: str) -> dict[str, str]:
    """Return guid_hex -> talent_key mapping for a hero."""
    yaml_path = HEROES_DIR / f"{hero_key}.yaml"
    if not yaml_path.exists():
        raise click.ClickException(f"hero registry not found: {yaml_path}")
    with yaml_path.open() as f:
        data = yaml.safe_load(f)
    out: dict[str, str] = {}
    for c in data.get("controllers", []):
        guid = c.get("guid")
        key = c.get("key")
        if guid and key:
            out[guid] = key
    return out


def _parse_log_entry(
    log_path: Path, entry: str
) -> tuple[int, int, int, list[str]]:
    """Find a `[#N] pool: ...` block in the log and extract its inner-deref
    bytes per pool index.

    Returns (entry_num, count, slot, [inner_hex_per_index]).
    `entry` is "latest" or a numeric string.
    """
    text = log_path.read_text(errors="replace").splitlines()

    # Find all entry numbers that have a `pool: slot=` line.
    pool_header_re = re.compile(
        r"\[#(\d+)\]\s+pool:\s+slot=(\d+)\s+class=(\d+)\s+count=(\d+)"
    )
    inner_re = re.compile(
        r"\[#(\d+)\]\s+pool\[(\d+)\]\s+inner\s*=\s*([0-9a-fA-F]+)"
    )

    headers: dict[int, tuple[int, int, int]] = {}  # entry_num -> (slot, class, count)
    for line in text:
        m = pool_header_re.search(line)
        if m:
            n = int(m.group(1))
            headers[n] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))

    if not headers:
        raise click.ClickException(
            f"no `pool: slot=...` header lines found in {log_path}; "
            f"did you arm dumpTalentPoolNext() before a picker fired?"
        )

    if entry == "latest":
        entry_num = max(headers)
    else:
        try:
            entry_num = int(entry)
        except ValueError:
            raise click.ClickException(
                f"--entry must be 'latest' or an integer, got {entry!r}"
            )
        if entry_num not in headers:
            raise click.ClickException(
                f"entry [#{entry_num}] not found. Available: "
                f"{sorted(headers.keys())[-10:]} (latest 10 shown)"
            )

    slot, class_idx, count = headers[entry_num]

    # Collect inner-hex lines for this entry.
    inner_by_idx: dict[int, str] = {}
    for line in text:
        m = inner_re.search(line)
        if m and int(m.group(1)) == entry_num:
            inner_by_idx[int(m.group(2))] = m.group(3).lower()

    if len(inner_by_idx) != count:
        raise click.ClickException(
            f"entry [#{entry_num}] has count={count} but {len(inner_by_idx)} "
            f"inner-dump lines — log may be truncated. Need to re-run with "
            f"the GUID-extraction inner-dump (256-byte version)."
        )
    inners = [inner_by_idx[i] for i in range(count)]
    return entry_num, count, slot, inners


def _map_pool_to_talents(
    inners: list[str], guid_to_key: dict[str, str]
) -> list[tuple[int, str | None, str | None]]:
    """For each pool index, scan the inner-hex bytes for any known hero GUID
    and map to (idx, talent_key, guid_hex). Returns None entries for pool
    items whose GUID didn't match the registry (likely non-talent placeholders).
    """
    out = []
    for i, hex_str in enumerate(inners):
        matched_key = None
        matched_guid = None
        for guid_hex, key in guid_to_key.items():
            if guid_hex in hex_str:
                matched_key = key
                matched_guid = guid_hex
                break
        out.append((i, matched_key, matched_guid))
    return out


@experimental_grp.command(
    name="find-talent-seeds",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--hero",
    required=True,
    type=str,
    metavar="<key>",
    help="Hero key (matches data/heroes/<key>.yaml).",
)
@click.option(
    "--target",
    required=True,
    type=str,
    metavar="<key1,key2,...>",
    help="Comma-separated talent keys you want the picker to offer.",
)
@click.option(
    "--log",
    "log_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    metavar="<path>",
    help="Frida diagnostic log containing the pool dump.",
)
@click.option(
    "--entry",
    default="latest",
    type=str,
    metavar="<latest|N>",
    help="Which `[#N]` picker entry's pool block to use (default: latest).",
)
@click.option(
    "--num-picks",
    default=None,
    type=int,
    metavar="<int>",
    help="Number of talents the picker offers. Default: len(target).",
)
@click.option(
    "--limit",
    default=5,
    type=int,
    metavar="<int>",
    help="Stop after this many matching seeds (default 5).",
)
@click.option(
    "--seed-start",
    default=0,
    type=int,
    metavar="<int>",
    help="Seed to start brute-force from (default 0).",
)
@click.option(
    "--seed-end",
    default=None,
    type=int,
    metavar="<int>",
    help="Seed to stop at (exclusive). Default: 2**31.",
)
def find_talent_seeds_cmd(
    hero: str,
    target: str,
    log_path: Path,
    entry: str,
    num_picks: int | None,
    limit: int,
    seed_start: int,
    seed_end: int | None,
) -> None:
    """EXPERIMENTAL: find a seed that produces the target picker proposal.

    Brute-forces uint32 seeds by simulating the inline PCG + Fisher-Yates
    selection in the talent picker, against the unpruned pool captured by
    Frida (`dumpTalentPoolNext()` + a triggered picker entry). Mirrors the
    algorithm in SkillController_roll_proposed_skills.

    \b
    Usage:
      1. In Frida REPL: dumpTalentPoolNext()
      2. Trigger a picker. The log gets a `[#N] pool:` block.
      3. rerw experimental find-talent-seeds \\
           --hero romeo --target FlashOfSteel,DeadlyBrambles \\
           --log /mnt/c/.../frida_seed_diag.log
      4. Use one of the printed seeds: forceFresh(<seed>) in Frida.
    """
    target_keys = [t.strip() for t in target.split(",") if t.strip()]
    if not target_keys:
        raise click.ClickException("--target must list at least one key")

    guid_to_key = _load_hero_talents(hero)
    info(f"hero {hero}: {len(guid_to_key)} talents in registry")

    entry_num, count, slot, inners = _parse_log_entry(log_path, entry)
    info(f"using log entry [#{entry_num}]: slot={slot}, pool count={count}")

    mapping = _map_pool_to_talents(inners, guid_to_key)
    name_to_idx: dict[str, int] = {}
    unidentified = 0
    for i, key, _ in mapping:
        if key is None:
            unidentified += 1
        else:
            if key in name_to_idx:
                # Same talent at multiple pool indices — log a warning but
                # proceed; the brute-force will still find seeds.
                click.echo(
                    f"warn: talent {key!r} appears at pool[{name_to_idx[key]}] "
                    f"AND pool[{i}]",
                    err=True,
                )
            name_to_idx[key] = i
    if unidentified:
        click.echo(
            f"warn: {unidentified}/{count} pool entries did not match any "
            f"known {hero} talent GUID",
            err=True,
        )

    missing = [t for t in target_keys if t not in name_to_idx]
    if missing:
        avail = sorted(name_to_idx.keys())
        raise click.ClickException(
            f"target talent(s) not in pool: {missing}\nAvailable: {avail}"
        )

    target_indices = {name_to_idx[t] for t in target_keys}
    picks = num_picks if num_picks is not None else len(target_keys)
    if picks != len(target_keys):
        click.echo(
            f"warn: --num-picks={picks} differs from len(target)={len(target_keys)}",
            err=True,
        )

    info(
        f"target indices: {sorted(target_indices)} "
        f"(num_picks={picks})"
    )

    pool = list(range(count))
    end = seed_end if seed_end is not None else (MASK31 + 1)
    info(f"brute-forcing seeds in [{seed_start}, {end})…")

    matches = find_seeds(
        pool,
        num_picks=picks,
        target=target_indices,
        seed_range=range(seed_start, end),
        limit=limit,
    )

    if not matches:
        click.echo("no matching seeds found in the given range")
        raise SystemExit(1)

    click.echo(f"\nfound {len(matches)} seed(s) producing target {target_keys}:")
    for s in matches:
        out, _ = simulate(s, pool, picks)
        names = [
            mapping[i][1] if mapping[i][1] else f"pool[{i}]"
            for i in out
        ]
        click.echo(f"  forceFresh(0x{s:08x})  =>  {names}")
