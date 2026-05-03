"""Tests for the talent-edit primitives.

The other functions in `lib.talent_edit` (`find_talent_record`,
`find_picks_count`, `read_picks`, `write_pick`, `read_rarity`, `write_rarity`,
`parse_rarity`) are exercised indirectly by `test_cli` and the
in-game-validated golden labs catalogued in `rw/key-findings/talent-records.md`.
The bulk-set primitives covered here get targeted unit coverage.

Validation strategy: against the epilogue-laser-lenses_1 proof — known to
contain 28 tag=0x10 controller records of which 4 are ult-marker (rarity=4).
Bulk-set should modify exactly 24 records and preserve the 4 ult-markers
(skip is hardcoded — value=4 entries are always preserved).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.talent_edit import (
    RARITY_OFFSET_FROM_GUID,
    SLOT_COUNT,
    SLOT_RARITY_ARRAY_OFFSET,
    TAG10_PRE_PATTERN,
    ULT_SLOT_INDEX,
    TalentEditError,
    find_talent_record,
    parse_rarity,
    write_all_rarity_bytes,
    write_all_slot_rarities,
)

# 15-byte talent record GUID — same across all Geppetto saves observed,
# presumed hero-independent per `rw/key-findings/talent-records.md`.
TALENT_RECORD_GUID_15 = bytes.fromhex(
    "bfe7f6604385cb4887f6b4b79f6812"
)

REPO_ROOT = Path(__file__).resolve().parents[3].parent
EPILOGUE_PROOF = (
    REPO_ROOT
    / "rw/saves/proofs/geppetto/epilogue/laser-lenses_1/Profile_1.ob"
)


@pytest.fixture
def epilogue_bytes() -> bytes:
    if not EPILOGUE_PROOF.is_file():
        pytest.skip(f"Epilogue proof missing: {EPILOGUE_PROOF}")
    return EPILOGUE_PROOF.read_bytes()


def _rarity_distribution(data: bytes) -> dict[int, int]:
    """Return {rarity_byte_value: count} across all tag=0x10 records."""
    counts: dict[int, int] = {}
    pos = 0
    while True:
        pos = data.find(TAG10_PRE_PATTERN, pos)
        if pos < 0:
            break
        rarity_byte = data[pos + len(TAG10_PRE_PATTERN) + RARITY_OFFSET_FROM_GUID]
        counts[rarity_byte] = counts.get(rarity_byte, 0) + 1
        pos += 1
    return counts


def test_write_all_rarity_bytes_to_legendary_skips_ult(
    epilogue_bytes: bytes,
) -> None:
    """Bulk-set to legendary preserves the 4 ult-marker records."""
    data = bytearray(epilogue_bytes)
    src_dist = _rarity_distribution(epilogue_bytes)
    # Sanity: epilogue has exactly 28 tag=0x10 records, 4 are ult-marker.
    assert sum(src_dist.values()) == 28
    assert src_dist.get(4, 0) == 4

    modified = write_all_rarity_bytes(data, rarity=3)
    # Modified count = 28 total - 4 ult-marker = 24.
    assert modified == 24

    out_dist = _rarity_distribution(bytes(data))
    # Result: 24 records at legendary (3) + 4 ult-markers (4) preserved.
    assert out_dist == {3: 24, 4: 4}


def test_write_all_rarity_bytes_idempotent(epilogue_bytes: bytes) -> None:
    """Running the same bulk-set twice yields the same bytes the second time."""
    data1 = bytearray(epilogue_bytes)
    write_all_rarity_bytes(data1, rarity=2)
    snap = bytes(data1)
    n = write_all_rarity_bytes(data1, rarity=2)
    assert n == 24  # same count
    assert bytes(data1) == snap


def test_write_all_rarity_bytes_each_rarity_value(
    epilogue_bytes: bytes,
) -> None:
    """Every rarity value 0..3 produces a clean post-state distribution."""
    for rarity_int in (0, 1, 2, 3):
        data = bytearray(epilogue_bytes)
        modified = write_all_rarity_bytes(data, rarity=rarity_int)
        assert modified == 24
        dist = _rarity_distribution(bytes(data))
        assert dist == {rarity_int: 24, 4: 4}


def test_write_all_rarity_bytes_rejects_out_of_range() -> None:
    data = bytearray(b"\x00" * 1024)
    with pytest.raises(TalentEditError, match="must be a u8"):
        write_all_rarity_bytes(data, rarity=-1)
    with pytest.raises(TalentEditError, match="must be a u8"):
        write_all_rarity_bytes(data, rarity=256)


def test_write_all_rarity_bytes_returns_zero_when_no_records() -> None:
    """A buffer with no tag=0x10 records returns 0 and isn't mutated."""
    data = bytearray(b"\x00" * 1024)
    snap = bytes(data)
    n = write_all_rarity_bytes(data, rarity=3)
    assert n == 0
    assert bytes(data) == snap


def test_parse_rarity_accepts_only_lowercase_names() -> None:
    """Strict surface: only the four lowercase rarity names are accepted."""
    assert parse_rarity("common") == 0
    assert parse_rarity("rare") == 1
    assert parse_rarity("epic") == 2
    assert parse_rarity("legendary") == 3


def test_parse_rarity_rejects_numeric_input() -> None:
    """Strict surface: numeric input is rejected."""
    with pytest.raises(TalentEditError, match="must be one of"):
        parse_rarity("0")
    with pytest.raises(TalentEditError, match="must be one of"):
        parse_rarity("3")


def test_parse_rarity_rejects_non_lowercase() -> None:
    """Strict surface: any case other than all-lowercase is rejected."""
    with pytest.raises(TalentEditError, match="must be one of"):
        parse_rarity("LEGENDARY")
    with pytest.raises(TalentEditError, match="must be one of"):
        parse_rarity("Epic")


def test_parse_rarity_rejects_unknown() -> None:
    with pytest.raises(TalentEditError, match="must be one of"):
        parse_rarity("mythic")


def _read_slot_rarities(data: bytes) -> list[int]:
    """Helper: read the 10-u32 slot.rarity array from the talent record."""
    rec_off = find_talent_record(data, TALENT_RECORD_GUID_15)
    arr_off = rec_off + SLOT_RARITY_ARRAY_OFFSET
    return [
        int.from_bytes(data[arr_off + i * 4 : arr_off + (i + 1) * 4], "little")
        for i in range(SLOT_COUNT)
    ]


def test_slot_rarities_recovered_from_epilogue_proof(
    epilogue_bytes: bytes,
) -> None:
    """The on-disk slot.rarity array shape: 10 entries each in [0..4]."""
    vals = _read_slot_rarities(epilogue_bytes)
    assert len(vals) == 10
    assert all(0 <= v <= 4 for v in vals)
    # Empirically verified for the laser-lenses_1 epilogue lineage.
    assert vals == [0, 3, 3, 0, 4, 3, 0, 1, 3, 3]


def test_write_all_slot_rarities_skips_ult_index(
    epilogue_bytes: bytes,
) -> None:
    """Bulk-set writes 9 entries — index-based skip preserves only the ult slot."""
    data = bytearray(epilogue_bytes)
    src_vals = _read_slot_rarities(epilogue_bytes)

    modified = write_all_slot_rarities(
        data, rarity=3, record_guid_15=TALENT_RECORD_GUID_15
    )
    # Index-based: skip exactly one entry (slot index 4 = user slot 5).
    assert modified == SLOT_COUNT - 1

    out_vals = _read_slot_rarities(bytes(data))
    # Slot index 4 (ult) preserved; all others overwritten to 3.
    for i, (src_v, out_v) in enumerate(zip(src_vals, out_vals)):
        if i == ULT_SLOT_INDEX:
            assert out_v == src_v
        else:
            assert out_v == 3


def test_write_all_slot_rarities_each_value(epilogue_bytes: bytes) -> None:
    """Every rarity value 0..3 writes correctly to all 9 non-ult slots."""
    src_vals = _read_slot_rarities(epilogue_bytes)
    for rarity_int in (0, 1, 2, 3):
        data = bytearray(epilogue_bytes)
        write_all_slot_rarities(
            data, rarity=rarity_int, record_guid_15=TALENT_RECORD_GUID_15
        )
        out = _read_slot_rarities(bytes(data))
        for i in range(SLOT_COUNT):
            if i == ULT_SLOT_INDEX:
                assert out[i] == src_vals[i]
            else:
                assert out[i] == rarity_int


def test_write_all_slot_rarities_rejects_out_of_range() -> None:
    data = bytearray(b"\x00" * 1024)
    with pytest.raises(TalentEditError, match="must be a u8"):
        write_all_slot_rarities(
            data, rarity=-1, record_guid_15=TALENT_RECORD_GUID_15
        )


def test_write_all_slot_rarities_raises_when_record_missing() -> None:
    data = bytearray(b"\x00" * 1024)
    with pytest.raises(TalentEditError, match="not found"):
        write_all_slot_rarities(
            data, rarity=3, record_guid_15=TALENT_RECORD_GUID_15
        )
