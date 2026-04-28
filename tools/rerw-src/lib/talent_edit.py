"""Talent-record edit primitives — pure logic, no Click or I/O policy.

Two structures are involved per save:

1. The tag=0x12 talent record holds the player's 5 talent picks. Located by
   its stable 15-byte record GUID. Inside its body, an 8-byte sentinel
   (`00 00 00 00 05 00 00 00`) anchors a 5×16-byte talent-pick block.

2. Per-controller tag=0x10 records (28 of them per hero) sit in the
   herodef-reference region near the hero record. Each is laid out as:
       [u32 tag = 0x10][16-byte talent GUID][1-byte flag = 0x01]
       [1-byte tier][3 bytes 0x00 padding]
   The byte at GUID+17 is the tier the engine reads for the HUD display.

Verified end-to-end for Geppetto via lab-swap experiments documented in
`rw/key-findings/talent-records.md`. The talent record GUID and structure
are presumed hero-independent.
"""

from __future__ import annotations

import re

GUID_LEN_16 = 16
TIER_OFFSET_FROM_GUID = 17  # 16 bytes of GUID + 1 byte of `0x01` flag
TAG10_PRE_PATTERN = b"\x11\x11\xbb\xaa\x10\x00\x00\x00"  # start marker + tag 0x10
HERO_PATH_RE = re.compile(rb"Heroes\\([A-Za-z_][A-Za-z_0-9]*)\.herodef\.ot")

TIER_NAMES = {
    "common": 0,
    "rare": 1,
    "epic": 2,
    "legendary": 3,
    "ult": 4,
    "ult_marker": 4,
}
TIER_VALUE_TO_NAME = {0: "Common", 1: "Rare", 2: "Epic", 3: "Legendary", 4: "ult-marker"}


class TalentEditError(ValueError):
    """Raised when a talent edit precondition fails."""


def detect_hero(data: bytes) -> str:
    """Return the hero name encoded in this save's `Heroes\\<Name>.herodef.ot`.

    Raises if the path string isn't found or doesn't match the expected shape.
    """
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


def find_picks_anchor(data: bytes, record_off: int, sentinel: bytes) -> int:
    """Find the talent-pick block start, given the talent record body start.

    Searches for the sentinel from `record_off` forward. Returns the offset
    of the FIRST talent GUID (i.e. anchor + len(sentinel)).
    """
    pos = data.find(sentinel, record_off)
    if pos < 0:
        raise TalentEditError(
            f"Talent-pick sentinel {sentinel.hex()} not found after record"
        )
    return pos + len(sentinel)


def read_picks(data: bytes, picks_start: int, slot_count: int = 5) -> list[bytes]:
    """Read all talent GUIDs in slot order (slot 1 = index 0)."""
    return [
        bytes(data[picks_start + i * GUID_LEN_16 : picks_start + (i + 1) * GUID_LEN_16])
        for i in range(slot_count)
    ]


def write_pick(
    data: bytearray, picks_start: int, slot: int, new_guid: bytes
) -> bytes:
    """Replace slot N's 16-byte talent GUID. Slot is 1-indexed.

    Returns the OLD 16-byte GUID for reporting.
    """
    if not 1 <= slot <= 5:
        raise TalentEditError(f"slot must be in 1..5, got {slot}")
    if len(new_guid) != GUID_LEN_16:
        raise TalentEditError(
            f"new_guid must be {GUID_LEN_16} bytes, got {len(new_guid)}"
        )
    off = picks_start + (slot - 1) * GUID_LEN_16
    old = bytes(data[off : off + GUID_LEN_16])
    data[off : off + GUID_LEN_16] = new_guid
    return old


def find_tag10_record(data: bytes, talent_guid_16: bytes) -> int:
    """Locate the tag=0x10 first-occurrence record for a talent GUID.

    Returns the offset of the talent GUID's first byte (i.e. immediately
    after the start marker + tag-0x10 prefix). The tier byte is at
    `(returned_offset + TIER_OFFSET_FROM_GUID)`.

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


def read_tier(data: bytes, talent_guid_16: bytes) -> int:
    """Read the tier byte from the tag=0x10 record for this talent."""
    guid_off = find_tag10_record(data, talent_guid_16)
    return data[guid_off + TIER_OFFSET_FROM_GUID]


def write_tier(data: bytearray, talent_guid_16: bytes, tier: int) -> int:
    """Write the tier byte for this talent's tag=0x10 record. Returns OLD tier."""
    if not 0 <= tier <= 255:
        raise TalentEditError(f"tier must be a u8 (0..255), got {tier}")
    guid_off = find_tag10_record(data, talent_guid_16)
    tier_off = guid_off + TIER_OFFSET_FROM_GUID
    old = data[tier_off]
    data[tier_off] = tier
    return old


def parse_tier(value: str | int) -> int:
    """Accept symbolic name (Common/Rare/Epic/Legendary) or 0..3 numeric."""
    if isinstance(value, int):
        return value
    s = str(value).strip().lower()
    if s.isdigit():
        return int(s)
    if s in TIER_NAMES:
        return TIER_NAMES[s]
    raise TalentEditError(
        f"Unknown tier {value!r}; expected one of "
        f"{sorted(set(TIER_NAMES.keys()))} or 0..3 numeric"
    )
