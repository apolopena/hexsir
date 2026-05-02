"""Magical-object record edit primitives — pure logic, no Click or I/O policy.

The player's collected magical objects (and powerups) are stored as
`tag=0x1a` records inside the single `tag=0x12` run-state record. Each
record is exactly 32 bytes:

    [marker        4: 11 11 bb aa]
    [tag           4: 1a 00 00 00]
    [runtime GUID 16: <hex>]
    [counter       4: u32 LE — sequence number]
    [close marker  4: 22 22 bb aa]

Records-array layout, relative to the run-state tag-byte offset (`pos`):

    pos + 0x5d: u32 LE — items count
    pos + 0x61: records array — count × 32 bytes
    pos + 0x61 + count*32: trailing block (set-bonus tracker, talent block,
                           per-save scalar, run-state close marker)

The run-state record has no outer length prefix; the marker/close framing
self-terminates. Splices propagate naturally — caller recomputes CRC.

See `rw/key-findings/magical-objects.md` for the canonical reference and
the Engine-validation gotchas (Rule A fresh-ref cap, Rule B per-item
threshold cap, Rule C total-record-count cap). This module produces
syntactically valid records; respecting per-save engine ceilings is the
caller's responsibility.

Status: SWAP, ADD, REMOVE primitives all verified end-to-end on the
Geppetto chapter-2 Save A — verified-working lab/golden artifacts under
`rw/saves/edits/{lab,golden}/geppetto/...` are the byte-level test fixtures.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# Run-state record (tag=0x12) GUID. Same record holds magical-object
# records AND the talent picks block; talent_edit references this same
# GUID for talent operations.
RUN_STATE_RECORD_GUID_15 = bytes.fromhex("bfe7f6604385cb4887f6b4b79f6812")
RUN_STATE_TAG = b"\x12\x00\x00\x00"
ITEM_TAG = b"\x1a\x00\x00\x00"
MARK_START = b"\x11\x11\xbb\xaa"
MARK_END = b"\x22\x22\xbb\xaa"

ITEM_RECORD_SIZE = 32
RUNTIME_GUID_LEN = 16

# Offsets within the run-state record, relative to the tag-byte offset:
ITEMS_COUNT_OFFSET = 0x5D  # u32 LE: number of item records
RECORDS_ARRAY_OFFSET = 0x61  # first item record marker


class ItemEditError(ValueError):
    """Raised when an item-record edit precondition fails."""


@dataclass(frozen=True)
class ItemRecord:
    """A parsed `tag=0x1a` item record."""

    slot: int  # 1-indexed slot in record-array order (== counter order in observed saves)
    offset: int  # absolute file offset of the record's MARK_START byte
    runtime_guid: bytes
    counter: int


def find_run_state(data: bytes) -> int:
    """Locate the unique tag=0x12 run-state record.

    Returns:
        The absolute offset of the type-tag byte (start of `12 00 00 00`).

    Raises:
        ItemEditError: if the run-state record is not present in `data`.
    """
    needle = RUN_STATE_TAG + RUN_STATE_RECORD_GUID_15
    pos = data.find(needle)
    if pos < 0:
        raise ItemEditError("Run-state record (tag=0x12) not found in save")
    return pos


def parse_records(data: bytes) -> list[ItemRecord]:
    """Walk the records array and return one ItemRecord per slot.

    Raises:
        ItemEditError: if any record's marker / tag / close framing is
            malformed (indicates a corrupt save or a mis-located run-state).
    """
    pos = find_run_state(data)
    count = struct.unpack_from("<I", data, pos + ITEMS_COUNT_OFFSET)[0]
    records: list[ItemRecord] = []
    for i in range(count):
        rec_off = pos + RECORDS_ARRAY_OFFSET + i * ITEM_RECORD_SIZE
        if data[rec_off : rec_off + 4] != MARK_START:
            raise ItemEditError(
                f"Record {i + 1} at 0x{rec_off:x} missing MARK_START "
                f"(got {data[rec_off : rec_off + 4].hex()})"
            )
        if data[rec_off + 4 : rec_off + 8] != ITEM_TAG:
            raise ItemEditError(
                f"Record {i + 1} at 0x{rec_off:x} missing tag=0x1a "
                f"(got {data[rec_off + 4 : rec_off + 8].hex()})"
            )
        if data[rec_off + 28 : rec_off + 32] != MARK_END:
            raise ItemEditError(
                f"Record {i + 1} at 0x{rec_off:x} missing MARK_END "
                f"(got {data[rec_off + 28 : rec_off + 32].hex()})"
            )
        runtime_guid = bytes(data[rec_off + 8 : rec_off + 24])
        counter = struct.unpack_from("<I", data, rec_off + 24)[0]
        records.append(
            ItemRecord(
                slot=i + 1, offset=rec_off, runtime_guid=runtime_guid, counter=counter
            )
        )
    return records


def _validate_runtime_guid(runtime_guid: bytes) -> None:
    if len(runtime_guid) != RUNTIME_GUID_LEN:
        raise ItemEditError(
            f"runtime_guid must be {RUNTIME_GUID_LEN} bytes, "
            f"got {len(runtime_guid)}"
        )


def swap_item(
    data: bytearray, slot: int, new_runtime_guid: bytes
) -> bytes:
    """Replace slot N's runtime GUID with `new_runtime_guid`.

    Mutates `data` in place. Constant-size; no body shift. Returns the
    previous runtime GUID. The caller is responsible for recomputing
    the file CRC32.

    Args:
        data: Mutable raw save bytes.
        slot: 1-indexed slot in record-array order.
        new_runtime_guid: 16-byte runtime GUID to install.

    Raises:
        ItemEditError: if `slot` is out of range or `new_runtime_guid`
            is not 16 bytes.
    """
    _validate_runtime_guid(new_runtime_guid)
    records = parse_records(bytes(data))
    if not (1 <= slot <= len(records)):
        raise ItemEditError(
            f"slot {slot} out of range (valid: 1..{len(records)})"
        )
    rec = records[slot - 1]
    guid_off = rec.offset + 8
    old_guid = bytes(data[guid_off : guid_off + RUNTIME_GUID_LEN])
    data[guid_off : guid_off + RUNTIME_GUID_LEN] = new_runtime_guid
    return old_guid


def add_item(
    data: bytearray,
    runtime_guid: bytes,
    *,
    reuse_counter_from_slot: int | None = None,
) -> int:
    """Append a new item record at the end of the records array.

    Mutates `data` in place; the buffer grows by 32 bytes. Increments
    the items-count u32 at the run-state header. Returns the new total
    item count. The caller is responsible for recomputing the file CRC32.

    Args:
        data: Mutable raw save bytes.
        runtime_guid: 16-byte runtime GUID of the item to add.
        reuse_counter_from_slot: 1-indexed slot whose counter to reuse for
            the new record. When None (default), uses `last_counter + 1`
            (allocates a fresh reference). Reusing an existing slot's
            counter bypasses the per-save Rule A fresh-reference cap;
            see `rw/key-findings/magical-objects.md` for the rules.

    Raises:
        ItemEditError: if `runtime_guid` is not 16 bytes, the records
            array is empty (cannot derive a base counter), or
            `reuse_counter_from_slot` is out of range.
    """
    _validate_runtime_guid(runtime_guid)
    records = parse_records(bytes(data))
    if not records:
        raise ItemEditError(
            "Cannot ADD on a save with zero existing item records: no base "
            "counter available. Use a save that already has at least one record."
        )
    if reuse_counter_from_slot is None:
        counter = records[-1].counter + 1
    else:
        if not (1 <= reuse_counter_from_slot <= len(records)):
            raise ItemEditError(
                f"reuse_counter_from_slot {reuse_counter_from_slot} out of range "
                f"(valid: 1..{len(records)})"
            )
        counter = records[reuse_counter_from_slot - 1].counter

    pos = find_run_state(bytes(data))
    insert_off = pos + RECORDS_ARRAY_OFFSET + len(records) * ITEM_RECORD_SIZE
    new_record = (
        MARK_START
        + ITEM_TAG
        + runtime_guid
        + struct.pack("<I", counter)
        + MARK_END
    )
    if len(new_record) != ITEM_RECORD_SIZE:
        raise ItemEditError(
            f"Internal error: new record is {len(new_record)} bytes, "
            f"expected {ITEM_RECORD_SIZE}"
        )
    data[insert_off:insert_off] = new_record
    new_count = len(records) + 1
    struct.pack_into("<I", data, pos + ITEMS_COUNT_OFFSET, new_count)
    return new_count


def remove_item(data: bytearray, slot: int) -> bytes:
    """Remove slot N's record from the records array.

    Mutates `data` in place; the buffer shrinks by 32 bytes. Decrements
    the items-count u32 at the run-state header. Returns the removed
    record's runtime GUID. The caller is responsible for recomputing
    the file CRC32.

    Args:
        data: Mutable raw save bytes.
        slot: 1-indexed slot to remove.

    Raises:
        ItemEditError: if `slot` is out of range.
    """
    records = parse_records(bytes(data))
    if not (1 <= slot <= len(records)):
        raise ItemEditError(
            f"slot {slot} out of range (valid: 1..{len(records)})"
        )
    rec = records[slot - 1]
    removed_guid = bytes(data[rec.offset + 8 : rec.offset + 24])
    del data[rec.offset : rec.offset + ITEM_RECORD_SIZE]
    pos = find_run_state(bytes(data))
    new_count = len(records) - 1
    struct.pack_into("<I", data, pos + ITEMS_COUNT_OFFSET, new_count)
    return removed_guid
