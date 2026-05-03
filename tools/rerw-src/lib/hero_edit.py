"""Hero-record edit primitives — pure logic, no Click or I/O policy.

The hero is encoded in the save body as a length-prefixed ASCII path:

    [u32 length prefix LE][ASCII path bytes]
    e.g. `(26)(Heroes\\Geppetto.herodef.ot)`

The path always takes the form `Heroes\\<EngineName>.herodef.ot`; replacing
it changes the hero on load. Same-length swaps leave file size unchanged;
different-length swaps shift every byte after the path by the name-length
delta.

Verified end-to-end (`rw/findings/hero-swaps.md`, MAINT-8) across four
swaps from the chapter-2 Geppetto proof:
    Carmilla    (no shift)
    Aladdin     (-1 byte)
    Snow_Queen  (+2 bytes)
    Red         (-5 bytes)
"""

from __future__ import annotations

import struct

from lib.talent_edit import HERO_PATH_RE


class HeroEditError(ValueError):
    """Raised when a hero-record edit precondition fails."""


def find_hero_record(data: bytes) -> tuple[int, int, str]:
    """Locate the unique hero-record length prefix + path in a save.

    Args:
        data: Raw save bytes.

    Returns:
        `(length_prefix_offset, path_offset, current_engine_name)`. The path
        starts at `path_offset` and runs `length_prefix_value` bytes; the
        length prefix is the four bytes immediately preceding `path_offset`.

    Raises:
        HeroEditError: if the `Heroes\\<Name>.herodef.ot` pattern is missing,
            appears more than once, has no room for a 4-byte length prefix,
            or the length prefix value does not equal the actual path length.
    """
    matches = list(HERO_PATH_RE.finditer(data))
    if not matches:
        raise HeroEditError(
            "Hero path string `Heroes\\<Name>.herodef.ot` not found in save"
        )
    if len(matches) > 1:
        offsets = ", ".join(f"0x{m.start():x}" for m in matches)
        raise HeroEditError(
            f"Expected exactly one hero path string in save; "
            f"found {len(matches)} at offsets [{offsets}]"
        )
    m = matches[0]
    path_off = m.start()
    path_len = m.end() - m.start()
    prefix_off = path_off - 4
    if prefix_off < 0:
        raise HeroEditError(
            f"Hero path at offset 0x{path_off:x} has no room for "
            f"a 4-byte length prefix"
        )
    declared_len = struct.unpack_from("<I", data, prefix_off)[0]
    if declared_len != path_len:
        raise HeroEditError(
            f"Hero path length prefix at 0x{prefix_off:x} = {declared_len}, "
            f"but actual path length = {path_len}"
        )
    return prefix_off, path_off, m.group(1).decode("ascii")


def swap_hero(data: bytearray, new_save_ref: str) -> tuple[str, str]:
    """Splice a new hero path into the save. Mutates `data` in place.

    Args:
        data: Mutable raw save bytes. The buffer's length will change by
            `len(new_engine_name) - len(old_engine_name)` bytes.
        new_save_ref: Canonical save reference, exactly
            `Heroes\\<EngineName>.herodef.ot` — typically obtained from
            `lib.game_registry.heroes().lookup(key).save_ref`.

    Returns:
        `(old_engine_name, new_engine_name)`. The caller is responsible
        for recomputing the file CRC32 over the post-edit body.

    Raises:
        HeroEditError: if `new_save_ref` does not match the expected
            pattern, or if the source save has no resolvable hero record.
    """
    new_path_bytes = new_save_ref.encode("ascii")
    new_match = HERO_PATH_RE.fullmatch(new_path_bytes)
    if new_match is None:
        raise HeroEditError(
            f"new_save_ref {new_save_ref!r} does not match "
            f"`Heroes\\<EngineName>.herodef.ot`"
        )
    new_engine_name = new_match.group(1).decode("ascii")
    prefix_off, path_off, old_engine_name = find_hero_record(bytes(data))
    old_path_len = struct.unpack_from("<I", data, prefix_off)[0]
    new_prefix = struct.pack("<I", len(new_path_bytes))
    data[prefix_off : path_off + old_path_len] = new_prefix + new_path_bytes
    return old_engine_name, new_engine_name
