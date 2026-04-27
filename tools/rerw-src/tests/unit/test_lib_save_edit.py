"""Tests for lib.save_edit primitives."""

import struct
import zlib

import pytest
from lib.save_edit import (
    compute_crc,
    find_guid_offset,
    get_crc,
    read_field,
    recompute_crc,
    write_field,
)
from lib.save_fields import Field

GUID_A = bytes.fromhex("aa" * 15)
GUID_B = bytes.fromhex("bb" * 15)


def _make_save(values: dict[bytes, int], extra_pad: int = 32) -> bytearray:
    """Build a synthetic save: 16-byte header + body containing the GUIDs."""
    body = bytearray()
    body.extend(b"\x00" * 8)  # leading body padding
    for guid, val in values.items():
        body.extend(guid)
        body.extend(struct.pack("<i", val))
        body.extend(b"\x00" * extra_pad)

    header = bytearray(16)
    # Place a stale CRC; the test will recompute.
    header[12:16] = b"\xde\xad\xbe\xef"
    return header + body


def _field(name: str, guids: tuple[bytes, ...]) -> Field:
    return Field(
        name=name,
        category="scalar",
        type="int32_le",
        guids=guids,
        description="",
    )


def test_get_and_compute_crc_roundtrip():
    save = _make_save({GUID_A: 7})
    expected = zlib.crc32(bytes(save[16:])) & 0xFFFFFFFF
    new_crc = recompute_crc(save)
    assert new_crc == expected
    assert get_crc(save) == expected
    assert compute_crc(save) == expected


def test_find_guid_offset_hits_and_misses():
    save = _make_save({GUID_A: 1})
    pos = find_guid_offset(save, GUID_A)
    assert pos is not None
    assert save[pos : pos + 15] == GUID_A
    assert find_guid_offset(save, GUID_B) is None


def test_read_field_returns_none_when_missing():
    save = _make_save({})
    f = _field("chapter", (GUID_A,))
    assert read_field(save, f) is None


def test_read_field_first_guid_wins():
    """When multiple GUIDs hold the same value, read returns it."""
    save = _make_save({GUID_A: 2, GUID_B: 2})
    f = _field("chapter", (GUID_A, GUID_B))
    assert read_field(save, f) == 2


def test_write_field_writes_all_guids_in_lockstep():
    save = _make_save({GUID_A: 2, GUID_B: 2})
    f = _field("chapter", (GUID_A, GUID_B))
    located = write_field(save, f, 5)
    assert len(located) == 2
    # Old values reported as 2, 2.
    assert [old for _, _, old in located] == [2, 2]
    assert read_field(save, f) == 5
    # Verify both records changed.
    posA = save.find(GUID_A)
    posB = save.find(GUID_B)
    assert struct.unpack("<i", save[posA + 15 : posA + 19])[0] == 5
    assert struct.unpack("<i", save[posB + 15 : posB + 19])[0] == 5


def test_write_field_raises_when_no_guid_present():
    save = _make_save({})
    f = _field("chapter", (GUID_A, GUID_B))
    with pytest.raises(ValueError, match="not present"):
        write_field(save, f, 0)


def test_write_field_skips_missing_guids_but_writes_present_ones():
    """If only some GUIDs are present, write the present ones and report them."""
    save = _make_save({GUID_A: 2})
    f = _field("chapter", (GUID_A, GUID_B))
    located = write_field(save, f, 9)
    assert len(located) == 1
    assert located[0][0] == GUID_A
    assert read_field(save, f) == 9


def test_unsupported_type_rejected():
    save = _make_save({GUID_A: 0})
    f = Field(
        name="x", category="scalar", type="float64_be", guids=(GUID_A,), description=""
    )
    with pytest.raises(ValueError, match="Unsupported field type"):
        read_field(save, f)
    with pytest.raises(ValueError, match="Unsupported field type"):
        write_field(save, f, 0)


def test_negative_int32_roundtrips():
    """Ensure signed encoding doesn't lose negatives (int32_le)."""
    save = _make_save({GUID_A: 0})
    f = _field("x", (GUID_A,))
    write_field(save, f, -1)
    assert read_field(save, f) == -1
