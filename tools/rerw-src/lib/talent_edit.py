"""Talent-record edit primitives — pure logic, no Click or I/O policy.

Two structures are involved per save:

1. The tag=0x12 talent record holds the player's N talent picks for the run
   (N varies by chapter: 5 at chapter-2 entry, up to 10 at epilogue). Located
   by its stable 15-byte record GUID. The picks block layout is uniform:
   `[u32 N count][N × 16-byte talent GUIDs]` followed by a fixed trailer
   `[8 zero bytes][float timing][8 zero bytes][22 22 bb aa close marker]`.

2. Per-controller tag=0x10 records (typically 28 per hero) sit in the
   herodef-reference region near the hero record. Each is laid out as:
       [u32 tag = 0x10][16-byte talent GUID][1-byte flag = 0x01]
       [1-byte rarity][3 bytes 0x00 padding]
   The byte at GUID+17 is the rarity the engine reads for HUD display.

Verified end-to-end for Geppetto across chapter-2 / chapter-3 / epilogue
proofs (`rw/scripts/inspect_picks_block.py`, 2026-05-03). Talent record GUID
and structure are presumed hero-independent.
"""

from __future__ import annotations

import re
import struct

GUID_LEN_16 = 16
RARITY_OFFSET_FROM_GUID = 17  # 16 bytes of GUID + 1 byte of `0x01` flag
TAG10_PRE_PATTERN = b"\x11\x11\xbb\xaa\x10\x00\x00\x00"  # start marker + tag 0x10
HERO_PATH_RE = re.compile(rb"Heroes\\([A-Za-z_][A-Za-z_0-9]*)\.herodef\.ot")

# Per-slot rarity u32 array offset, from the tag=0x12 talent record's tag byte.
# Verified empirically stable across chapter-2/3/epilogue proofs. Each entry is
# a u32 in [0..4]: 0=Common, 1=Rare, 2=Epic, 3=Legendary, 4=ult-marker /
# uninitialized sentinel.
SLOT_RARITY_ARRAY_OFFSET = 0x35
SLOT_COUNT = 10
ULT_SLOT_INDEX = 4  # zero-indexed; user slot 5

# Picks-block locator constants.
RUN_STATE_CLOSE_MARKER = b"\x22\x22\xbb\xaa"
TRAILER_PRE_FLOAT_PAD = 8
TRAILER_POST_FLOAT_PAD = 8
TRAILER_LEN = TRAILER_PRE_FLOAT_PAD + 4 + TRAILER_POST_FLOAT_PAD  # 20 bytes before close
TIMING_FLOAT_MIN = 100.0
TIMING_FLOAT_MAX = 5000.0
MAX_PICKS_COUNT = 15  # search bound for back-fitting N

RARITY_VALUES = ("common", "rare", "epic", "legendary")
RARITY_NAMES = {name: i for i, name in enumerate(RARITY_VALUES)}
RARITY_VALUE_TO_NAME = {i: name.capitalize() for i, name in enumerate(RARITY_VALUES)}
RARITY_VALUE_TO_NAME[4] = "ult-marker"


class TalentEditError(ValueError):
    """Raised when a talent edit precondition fails."""


def detect_hero(data: bytes) -> str:
    """Return the hero name encoded in this save's `Heroes\\<Name>.herodef.ot`."""
    m = HERO_PATH_RE.search(data)
    if m is None:
        raise TalentEditError(
            "Hero path string `Heroes\\<Name>.herodef.ot` not found in save"
        )
    return m.group(1).decode("ascii")


def find_talent_record(data: bytes, record_guid_15: bytes) -> int:
    """Locate the talent record's body start (the type-tag offset).

    Searches for `[type-tag 0x12][record_guid_15]`. Returns the offset of the
    type-tag byte. Raises if not found.
    """
    if len(record_guid_15) != 15:
        raise TalentEditError(
            f"record_guid must be 15 bytes, got {len(record_guid_15)}"
        )
    needle = b"\x12\x00\x00\x00" + record_guid_15
    pos = data.find(needle)
    if pos < 0:
        raise TalentEditError("Talent record not found in save")
    return pos


def find_picks_count(data: bytes, record_off: int) -> tuple[int, int]:
    """Locate the picks-count u32 inside the talent record, count-agnostic.

    Walks back from the run-state-record close marker `22 22 bb aa` past the
    fixed trailer `[8 zero][float][8 zero]` to find picks-block end. Then
    back-fits a `[u32 N][N × 16 bytes]` shape ending there, for N in 1..15.

    Returns (picks_count_offset, count_value). Picks GUIDs occupy
    `picks_count_offset + 4 .. picks_count_offset + 4 + count*16`.

    Replaces the chapter-2-only `00 00 00 00 05 00 00 00` sentinel search.
    See `rw/findings/talent-records.md` § "Picks-block locator".
    """
    cursor = data.find(RUN_STATE_CLOSE_MARKER, record_off)
    while cursor >= 0:
        if cursor < TRAILER_LEN:
            cursor = data.find(RUN_STATE_CLOSE_MARKER, cursor + 4)
            continue
        pre = data[cursor - TRAILER_LEN : cursor]
        if (
            pre[:TRAILER_PRE_FLOAT_PAD] == b"\x00" * TRAILER_PRE_FLOAT_PAD
            and pre[TRAILER_PRE_FLOAT_PAD + 4 :] == b"\x00" * TRAILER_POST_FLOAT_PAD
        ):
            f_val = struct.unpack_from("<f", pre, TRAILER_PRE_FLOAT_PAD)[0]
            # Accept f_val == 0.0 (mint zeroes per-run timing stats including
            # this float) AND the populated-run range. The 8-zero/8-zero
            # sandwich + close marker is already a strong structural signature;
            # keeping a permissive sanity check here without rejecting valid
            # post-mint saves.
            if f_val == 0.0 or TIMING_FLOAT_MIN < f_val < TIMING_FLOAT_MAX:
                picks_end = cursor - TRAILER_LEN
                # Try N=1..MAX first (non-zero picks). N=0 last so we don't
                # falsely match coincidental zero u32s inside GUID bytes.
                for n in range(1, MAX_PICKS_COUNT + 1):
                    count_off = picks_end - n * GUID_LEN_16 - 4
                    if count_off <= record_off:
                        continue
                    count = struct.unpack_from("<I", data, count_off)[0]
                    if count == n:
                        return count_off, n
                # N=0 fallback: cleared-picks save (post `clear-picks`).
                count_off = picks_end - 4
                if count_off > record_off:
                    count = struct.unpack_from("<I", data, count_off)[0]
                    if count == 0:
                        return count_off, 0
        cursor = data.find(RUN_STATE_CLOSE_MARKER, cursor + 4)
    raise TalentEditError(
        f"Could not locate picks-count u32 after talent record at 0x{record_off:x}"
    )


def read_picks(data: bytes, picks_count_off: int, count: int) -> list[bytes]:
    """Read all talent GUIDs in slot order (slot 1 = list index 0)."""
    picks_start = picks_count_off + 4
    return [
        bytes(
            data[picks_start + i * GUID_LEN_16 : picks_start + (i + 1) * GUID_LEN_16]
        )
        for i in range(count)
    ]


def write_pick(
    data: bytearray, picks_count_off: int, count: int, slot: int, new_guid: bytes
) -> bytes:
    """Replace slot N's 16-byte talent GUID. `slot` is 1-indexed.

    Returns the OLD 16-byte GUID for reporting.
    """
    if not 1 <= slot <= count:
        raise TalentEditError(
            f"slot must be in 1..{count} for this save; got {slot}"
        )
    if len(new_guid) != GUID_LEN_16:
        raise TalentEditError(
            f"new_guid must be {GUID_LEN_16} bytes, got {len(new_guid)}"
        )
    off = picks_count_off + 4 + (slot - 1) * GUID_LEN_16
    old = bytes(data[off : off + GUID_LEN_16])
    data[off : off + GUID_LEN_16] = new_guid
    return old


def clear_picks(data: bytearray, record_guid_15: bytes) -> int:
    """Set picks count to 0 AND delete the N×16 bytes of GUIDs.

    Produces the "all 10 slots empty" state on load — the engine treats the
    save as "no picks made yet" and fires picker invocations on level-up. File
    shrinks by N×16 bytes. CRC must be recomputed by the caller.

    Returns the old N (number of GUIDs deleted) for reporting.
    """
    record_off = find_talent_record(data, record_guid_15)
    count_off, count = find_picks_count(data, record_off)
    data[count_off : count_off + 4] = b"\x00\x00\x00\x00"
    if count > 0:
        picks_start = count_off + 4
        del data[picks_start : picks_start + count * GUID_LEN_16]
    return count


def find_tag10_record(data: bytes, talent_guid_16: bytes) -> int:
    """Locate the tag=0x10 first-occurrence record for a talent GUID.

    Returns the offset of the talent GUID's first byte (i.e. immediately
    after the start marker + tag-0x10 prefix). The rarity byte is at
    `(returned_offset + RARITY_OFFSET_FROM_GUID)`.

    Raises if the talent GUID isn't preceded by the expected
    `[start marker][tag 0x10]` pattern.
    """
    if len(talent_guid_16) != GUID_LEN_16:
        raise TalentEditError(
            f"talent_guid must be {GUID_LEN_16} bytes, got {len(talent_guid_16)}"
        )
    pos = data.find(talent_guid_16)
    if pos < 0:
        raise TalentEditError(f"Talent GUID {talent_guid_16.hex()} not found")
    pre_start = pos - len(TAG10_PRE_PATTERN)
    if pre_start < 0 or bytes(data[pre_start:pos]) != TAG10_PRE_PATTERN:
        raise TalentEditError(
            f"Talent GUID at 0x{pos:x} is not preceded by tag=0x10 record marker; "
            f"actual pre-bytes: {bytes(data[max(0, pre_start) : pos]).hex()}"
        )
    return pos


def read_rarity(data: bytes, talent_guid_16: bytes) -> int:
    """Read the rarity byte from the tag=0x10 record for this talent."""
    guid_off = find_tag10_record(data, talent_guid_16)
    return data[guid_off + RARITY_OFFSET_FROM_GUID]


def write_rarity(data: bytearray, talent_guid_16: bytes, rarity: int) -> int:
    """Write the rarity byte for this talent's tag=0x10 record. Returns OLD rarity."""
    if not 0 <= rarity <= 255:
        raise TalentEditError(f"rarity must be a u8 (0..255), got {rarity}")
    guid_off = find_tag10_record(data, talent_guid_16)
    rarity_off = guid_off + RARITY_OFFSET_FROM_GUID
    old = data[rarity_off]
    data[rarity_off] = rarity
    return old


def parse_rarity(value: str) -> int:
    """Strict: only `common`, `rare`, `epic`, or `legendary` (lowercase)."""
    if not isinstance(value, str):
        raise TalentEditError(
            f"rarity must be a string, got {type(value).__name__}"
        )
    if value not in RARITY_NAMES:
        raise TalentEditError(
            f"rarity must be one of {list(RARITY_VALUES)} (lowercase only); got {value!r}"
        )
    return RARITY_NAMES[value]


def write_all_slot_rarities(
    data: bytearray,
    rarity: int,
    record_guid_15: bytes,
) -> int:
    """Bulk-set the per-slot rarity u32 array inside the tag=0x12 talent record.

    Writes `rarity` into 9 of the 10 entries, skipping the ult slot (zero-index 4).
    Index-based skip — does NOT skip uninitialized sentinels (value=4 in slots
    not yet picked), since those represent slots 6-10 the player hasn't reached
    yet, which we want stamped along with everything else.

    Returns the count of slot rarity entries modified (= 9 on success).
    """
    if not 0 <= rarity <= 255:
        raise TalentEditError(f"rarity must be a u8 (0..255), got {rarity}")
    record_off = find_talent_record(data, record_guid_15)
    array_off = record_off + SLOT_RARITY_ARRAY_OFFSET
    new_bytes = rarity.to_bytes(4, "little")
    count = 0
    for i in range(SLOT_COUNT):
        if i == ULT_SLOT_INDEX:
            continue
        slot_off = array_off + i * 4
        data[slot_off : slot_off + 4] = new_bytes
        count += 1
    return count


def write_all_rarity_bytes(data: bytearray, rarity: int) -> int:
    """Bulk-set the rarity byte on every tag=0x10 record in the save.

    Iterates `[start_marker][tag=0x10][16-byte GUID][flag][rarity byte]` records
    and overwrites the rarity byte at GUID+17. Records currently at the
    ult-marker sentinel (rarity byte = 4) are left untouched.

    Returns the count of records modified.
    """
    if not 0 <= rarity <= 255:
        raise TalentEditError(f"rarity must be a u8 (0..255), got {rarity}")
    pre = TAG10_PRE_PATTERN
    pre_len = len(pre)
    count = 0
    pos = 0
    while True:
        pos = data.find(pre, pos)
        if pos < 0:
            break
        guid_off = pos + pre_len
        rarity_off = guid_off + RARITY_OFFSET_FROM_GUID
        if data[rarity_off] == 4:
            pos += 1
            continue
        data[rarity_off] = rarity
        count += 1
        pos += 1
    return count
