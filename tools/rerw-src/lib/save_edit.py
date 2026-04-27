"""Core save-file edit primitives — pure logic, no Click or I/O policy.

Layout assumptions match `rw/scripts/mod_save.py`:
    bytes 0x0C..0x10  : CRC32 LE of body
    bytes 0x10..end   : body (CRC input)
    GUID matches      : value lives at GUID_offset + len(guid) (15 bytes)

Verified end-to-end via the chapter-rewind primitive
(see `rw/key-findings/save-chapter-counter.md`).
"""

from __future__ import annotations

import struct
import zlib

from lib.save_fields import Field

CRC_OFFSET = 0x0C
BODY_OFFSET = 0x10
GUID_LEN = 15


def get_crc(data: bytes) -> int:
    """Read the stored CRC32 from the save header."""
    return struct.unpack("<I", data[CRC_OFFSET : CRC_OFFSET + 4])[0]


def compute_crc(data: bytes) -> int:
    """Compute the CRC32 the body should have."""
    return zlib.crc32(data[BODY_OFFSET:]) & 0xFFFFFFFF


def recompute_crc(data: bytearray) -> int:
    """Recompute and write the CRC32 in place. Returns the new CRC."""
    new_crc = compute_crc(data)
    data[CRC_OFFSET : CRC_OFFSET + 4] = struct.pack("<I", new_crc)
    return new_crc


def find_guid_offset(data: bytes, guid: bytes) -> int | None:
    """Find a GUID in the save. Returns the GUID's start offset, or None."""
    pos = data.find(guid)
    return pos if pos != -1 else None


def _value_offset(guid_offset: int) -> int:
    return guid_offset + GUID_LEN


def _read_int32_le(data: bytes, offset: int) -> int:
    return struct.unpack("<i", data[offset : offset + 4])[0]


def _write_int32_le(data: bytearray, offset: int, value: int) -> None:
    data[offset : offset + 4] = struct.pack("<i", value)


def read_field(data: bytes, field: Field) -> int | None:
    """Read a field's current value from the save.

    Returns None if the field is absent (no GUID matches). When multiple
    GUIDs exist for one field, returns the value at the first GUID — the
    invariant is that all parallel GUIDs hold the same value.
    """
    if field.type != "int32_le":
        # TODO: extend to non-int32 value types as they're identified.
        raise ValueError(f"Unsupported field type: {field.type}")

    for guid in field.guids:
        gpos = find_guid_offset(data, guid)
        if gpos is not None:
            return _read_int32_le(data, _value_offset(gpos))
    return None


def write_field(
    data: bytearray, field: Field, value: int
) -> list[tuple[bytes, int, int]]:
    """Write a field's value across all of its GUIDs in place.

    Returns a list of `(guid, guid_offset, old_value)` tuples — one per GUID
    actually located in the save. Raises ValueError if no GUIDs are found
    (caller should treat this as a hard error: editing a missing field on
    a clean save would silently no-op otherwise).
    """
    if field.type != "int32_le":
        # TODO: extend to non-int32 value types as they're identified.
        raise ValueError(f"Unsupported field type: {field.type}")

    located: list[tuple[bytes, int, int]] = []
    for guid in field.guids:
        gpos = find_guid_offset(data, guid)
        if gpos is None:
            continue
        voff = _value_offset(gpos)
        old = _read_int32_le(data, voff)
        _write_int32_le(data, voff, value)
        located.append((guid, gpos, old))

    if not located:
        raise ValueError(
            f"Field '{field.name}' not present in save "
            f"(none of {len(field.guids)} GUID(s) matched)"
        )
    return located
