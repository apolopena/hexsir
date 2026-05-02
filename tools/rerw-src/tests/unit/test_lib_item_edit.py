"""Tests for the item-record edit primitives.

The strongest validation is byte-equality against three verified-working
reference artifacts under `rw/saves/edits/{lab,golden}/`. Each artifact
exercises one primitive end-to-end against the chapter-2 Geppetto Save A:

- SWAP: `lab/.../item-vorpal-blade-to-baba-yagas-mortar/` — slot 8, ghost GUID
- ADD:  `golden/.../item-add-fill-moonstone-stack-5of5/` — +2 Moonstone records
                                                            with fresh counters
- REMOVE: `lab/.../item-remove-last-record/` — drop slot 21

Reproducing each reference byte-for-byte through the production primitives
proves the bytes match what the engine validated and loaded successfully.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib import game_registry as registry
from lib.item_edit import (
    ItemEditError,
    add_item,
    find_run_state,
    parse_records,
    remove_item,
    swap_item,
)
from lib.save_edit import recompute_crc

REPO_ROOT = Path(__file__).resolve().parents[3].parent
SOURCE_PROOF = (
    REPO_ROOT / "rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob"
)

ADD_GOLDEN = (
    REPO_ROOT
    / "rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1"
    / "item-add-fill-moonstone-stack-5of5/Profile_1.ob"
)
SWAP_LAB = (
    REPO_ROOT
    / "rw/saves/edits/lab/geppetto/laser-lenses_1"
    / "item-vorpal-blade-to-baba-yagas-mortar/Profile_1.ob"
)
REMOVE_LAB = (
    REPO_ROOT
    / "rw/saves/edits/lab/geppetto/laser-lenses_1"
    / "item-remove-last-record/Profile_1.ob"
)

# Mortar ghost GUID — the destination of the SWAP lab. Not in the registry
# because it's a deprecated entity that reroutes to Water of Life on display.
MORTAR_GHOST_GUID = bytes.fromhex("1cc781a598b8314e9f52ae3c19d3edb3")


@pytest.fixture
def source_bytes() -> bytes:
    if not SOURCE_PROOF.is_file():
        pytest.skip(f"Source proof missing: {SOURCE_PROOF}")
    return SOURCE_PROOF.read_bytes()


def _read(path: Path) -> bytes:
    if not path.is_file():
        pytest.skip(f"Reference artifact missing: {path}")
    return path.read_bytes()


# --- find / parse -----------------------------------------------------------


def test_find_run_state_in_source(source_bytes: bytes) -> None:
    pos = find_run_state(source_bytes)
    # Chapter-2 proof's run-state record sits at file offset 0xee27.
    assert pos == 0xEE27


def test_find_run_state_missing_raises() -> None:
    with pytest.raises(ItemEditError, match="not found"):
        find_run_state(b"\x00" * 4096)


def test_parse_records_chapter_2(source_bytes: bytes) -> None:
    records = parse_records(source_bytes)
    # Chapter 2 has 21 records (14 magical objects + 7 powerups).
    assert len(records) == 21
    # First three Moonstones have counters 730/731/738; slot 1 = counter 730.
    assert records[0].counter == 730
    moon_guid = registry.magical_items().lookup("Moonstone").guid
    assert records[0].runtime_guid == moon_guid
    assert records[1].runtime_guid == moon_guid
    # Counters strictly increase by +1 per the doc.
    counters = [r.counter for r in records]
    assert counters == list(range(730, 730 + 21))


# --- SWAP -------------------------------------------------------------------


def test_swap_item_rejects_bad_guid_length(source_bytes: bytes) -> None:
    data = bytearray(source_bytes)
    with pytest.raises(ItemEditError, match="must be 16 bytes"):
        swap_item(data, 1, b"\x00" * 8)


def test_swap_item_rejects_out_of_range_slot(source_bytes: bytes) -> None:
    data = bytearray(source_bytes)
    moon_guid = registry.magical_items().lookup("Moonstone").guid
    with pytest.raises(ItemEditError, match="out of range"):
        swap_item(data, 0, moon_guid)
    with pytest.raises(ItemEditError, match="out of range"):
        swap_item(data, 22, moon_guid)


def test_swap_item_matches_verified_lab(source_bytes: bytes) -> None:
    """Slot-8 Vorpal Blade -> Mortar ghost reproduces the verified lab byte-for-byte."""
    data = bytearray(source_bytes)
    old_guid = swap_item(data, 8, MORTAR_GHOST_GUID)
    recompute_crc(data)

    expected_old = bytes.fromhex("cf7d88d6e39d0e488d0efbec81723360")
    assert old_guid == expected_old
    assert bytes(data) == _read(SWAP_LAB)


# --- ADD --------------------------------------------------------------------


def test_add_item_rejects_bad_guid_length(source_bytes: bytes) -> None:
    data = bytearray(source_bytes)
    with pytest.raises(ItemEditError, match="must be 16 bytes"):
        add_item(data, b"\x00" * 12)


def test_add_item_rejects_bad_reuse_slot(source_bytes: bytes) -> None:
    data = bytearray(source_bytes)
    moon_guid = registry.magical_items().lookup("Moonstone").guid
    with pytest.raises(ItemEditError, match="out of range"):
        add_item(data, moon_guid, reuse_counter_from_slot=99)


def test_add_item_fresh_counter_increments_last_plus_one(
    source_bytes: bytes,
) -> None:
    data = bytearray(source_bytes)
    moon_guid = registry.magical_items().lookup("Moonstone").guid
    new_count = add_item(data, moon_guid)
    assert new_count == 22
    records = parse_records(bytes(data))
    assert records[-1].counter == 751  # 750 + 1
    assert records[-1].runtime_guid == moon_guid


def test_add_item_reuse_counter_copies_from_slot(source_bytes: bytes) -> None:
    data = bytearray(source_bytes)
    moon_guid = registry.magical_items().lookup("Moonstone").guid
    add_item(data, moon_guid, reuse_counter_from_slot=9)  # slot 9 = counter 738
    records = parse_records(bytes(data))
    assert records[-1].counter == 738
    assert records[-1].runtime_guid == moon_guid


def test_add_item_fill_moonstone_5of5_matches_golden(source_bytes: bytes) -> None:
    """Two consecutive ADDs of Moonstone (counters 751, 752) reproduce the
    verified golden `item-add-fill-moonstone-stack-5of5` byte-for-byte."""
    data = bytearray(source_bytes)
    moon_guid = registry.magical_items().lookup("Moonstone").guid
    assert add_item(data, moon_guid) == 22
    assert add_item(data, moon_guid) == 23
    recompute_crc(data)
    assert bytes(data) == _read(ADD_GOLDEN)


# --- REMOVE -----------------------------------------------------------------


def test_remove_item_rejects_out_of_range_slot(source_bytes: bytes) -> None:
    data = bytearray(source_bytes)
    with pytest.raises(ItemEditError, match="out of range"):
        remove_item(data, 0)
    with pytest.raises(ItemEditError, match="out of range"):
        remove_item(data, 22)


def test_remove_last_record_matches_verified_lab(source_bytes: bytes) -> None:
    """Removing slot 21 reproduces the verified `item-remove-last-record`
    lab byte-for-byte."""
    data = bytearray(source_bytes)
    removed_guid = remove_item(data, 21)
    recompute_crc(data)

    # Slot 21 in chapter-2 = Philosopher's Stone (Vitality_Per_Health_Globe).
    expected_removed = bytes.fromhex("47db8829a3666e459b45aed07c03bdf2")
    assert removed_guid == expected_removed
    assert bytes(data) == _read(REMOVE_LAB)
    assert len(data) == len(source_bytes) - 32


def test_remove_then_add_round_trips_to_source(source_bytes: bytes) -> None:
    """Remove last + add same GUID with same counter returns to source bytes
    (modulo CRC, which is recomputed identically each time)."""
    data = bytearray(source_bytes)
    records_before = parse_records(source_bytes)
    last = records_before[-1]

    removed = remove_item(data, len(records_before))
    add_item(data, removed, reuse_counter_from_slot=None)
    # `reuse_counter_from_slot=None` after remove uses the new last+1 = 750,
    # which matches the slot we just removed.
    recompute_crc(data)
    assert bytes(data) == source_bytes
    # And the round-tripped record should match the original.
    records_after = parse_records(bytes(data))
    assert records_after[-1].runtime_guid == last.runtime_guid
    assert records_after[-1].counter == last.counter
