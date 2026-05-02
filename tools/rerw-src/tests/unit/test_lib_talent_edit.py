"""Tests for the talent-edit primitives, focused on `write_all_tier_bytes`.

The other functions in `lib.talent_edit` (`find_talent_record`,
`find_picks_anchor`, `read_picks`, `write_pick`, `read_tier`, `write_tier`,
`parse_tier`) are exercised indirectly by `test_cli` and the in-game-validated
golden labs catalogued in `rw/key-findings/talent-records.md`. The bulk-set
primitive added here is new and gets its own targeted unit coverage.

Validation strategy: against the epilogue-laser-lenses_1 proof — known to
contain 28 tag=0x10 controller records of which 4 are ult-marker (tier=4).
Bulk-set should modify exactly 24 records and preserve the 4 ult-markers
when `skip_ult_marker=True` (the default).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.talent_edit import (
    TAG10_PRE_PATTERN,
    TIER_OFFSET_FROM_GUID,
    TalentEditError,
    parse_tier,
    write_all_tier_bytes,
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


def _tier_distribution(data: bytes) -> dict[int, int]:
    """Return {tier_byte_value: count} across all tag=0x10 records."""
    counts: dict[int, int] = {}
    pos = 0
    while True:
        pos = data.find(TAG10_PRE_PATTERN, pos)
        if pos < 0:
            break
        tier_byte = data[pos + len(TAG10_PRE_PATTERN) + TIER_OFFSET_FROM_GUID]
        counts[tier_byte] = counts.get(tier_byte, 0) + 1
        pos += 1
    return counts


def test_write_all_tier_bytes_to_legendary_skips_ult(
    epilogue_bytes: bytes,
) -> None:
    """Bulk-set to legendary preserves the 4 ult-marker records by default."""
    data = bytearray(epilogue_bytes)
    src_dist = _tier_distribution(epilogue_bytes)
    # Sanity: epilogue has exactly 28 tag=0x10 records, 4 are ult-marker.
    assert sum(src_dist.values()) == 28
    assert src_dist.get(4, 0) == 4

    modified = write_all_tier_bytes(data, tier=3)
    # Modified count = 28 total - 4 ult-marker = 24.
    assert modified == 24

    out_dist = _tier_distribution(bytes(data))
    # Result: 24 records at legendary (3) + 4 ult-markers (4) preserved.
    assert out_dist == {3: 24, 4: 4}


def test_write_all_tier_bytes_no_skip_overrides_ult(
    epilogue_bytes: bytes,
) -> None:
    """With skip_ult_marker=False, ALL 28 records get rewritten."""
    data = bytearray(epilogue_bytes)
    modified = write_all_tier_bytes(data, tier=3, skip_ult_marker=False)
    assert modified == 28
    out_dist = _tier_distribution(bytes(data))
    assert out_dist == {3: 28}


def test_write_all_tier_bytes_idempotent(epilogue_bytes: bytes) -> None:
    """Running the same bulk-set twice yields the same bytes the second time."""
    data1 = bytearray(epilogue_bytes)
    write_all_tier_bytes(data1, tier=2)
    snap = bytes(data1)
    n = write_all_tier_bytes(data1, tier=2)
    assert n == 24  # same count
    assert bytes(data1) == snap


def test_write_all_tier_bytes_each_rarity_value(
    epilogue_bytes: bytes,
) -> None:
    """Every tier value 0..3 produces a clean post-state distribution."""
    for tier_int in (0, 1, 2, 3):
        data = bytearray(epilogue_bytes)
        modified = write_all_tier_bytes(data, tier=tier_int)
        assert modified == 24
        dist = _tier_distribution(bytes(data))
        assert dist == {tier_int: 24, 4: 4}


def test_write_all_tier_bytes_rejects_out_of_range() -> None:
    data = bytearray(b"\x00" * 1024)
    with pytest.raises(TalentEditError, match="must be a u8"):
        write_all_tier_bytes(data, tier=-1)
    with pytest.raises(TalentEditError, match="must be a u8"):
        write_all_tier_bytes(data, tier=256)


def test_write_all_tier_bytes_returns_zero_when_no_records() -> None:
    """A buffer with no tag=0x10 records returns 0 and isn't mutated."""
    data = bytearray(b"\x00" * 1024)
    snap = bytes(data)
    n = write_all_tier_bytes(data, tier=3)
    assert n == 0
    assert bytes(data) == snap


def test_parse_tier_accepts_rarity_names() -> None:
    """The CLI accepts both ints and rarity-name strings."""
    assert parse_tier("common") == 0
    assert parse_tier("rare") == 1
    assert parse_tier("epic") == 2
    assert parse_tier("legendary") == 3
    assert parse_tier("0") == 0
    assert parse_tier("3") == 3
    assert parse_tier(2) == 2


def test_parse_tier_case_insensitive() -> None:
    assert parse_tier("LEGENDARY") == 3
    assert parse_tier("Epic") == 2


def test_parse_tier_rejects_unknown() -> None:
    with pytest.raises(TalentEditError, match="Unknown tier"):
        parse_tier("mythic")
