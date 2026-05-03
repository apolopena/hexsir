"""Lab build: swap Geppetto epilogue proof's slot 6 talent to Twin Dummies.

Test A1 — verifies the generalized picks-block locator works for slot 6 writes
on a count=10 save (where the count=5 sentinel never matched).

Source: rw/saves/proofs/geppetto/epilogue/laser-lenses_1/Profile_1.ob (count=10)
Output: rw/saves/edits/lab/geppetto/laser-lenses_1/talent-slot6-to-twin-dummies__from-epilogue/Profile_1.ob

Locator strategy (matches `rw/scripts/inspect_picks_block.py`):
  Walk back from run-state-record close marker `22 22 bb aa` past the trailing
  `[8 zero][float][8 zero]` block. The picks block ends there. Find a u32 N at
  picks_end - 4 - N*16 such that reading N gives back the same N. That u32 is
  the picks count; the next N*16 bytes are slots 1..N.

Verification:
  Load the lab save in-game; HUD slot 6 should display Twin Dummies (instead
  of whatever the epilogue source had there).
"""

import struct
import zlib
from pathlib import Path

CRC_OFFSET = 0x0C
BODY_OFFSET = 0x10


def get_crc(data: bytes) -> int:
    return struct.unpack("<I", data[CRC_OFFSET : CRC_OFFSET + 4])[0]


def recompute_crc(data: bytearray) -> int:
    new_crc = zlib.crc32(data[BODY_OFFSET:]) & 0xFFFFFFFF
    data[CRC_OFFSET : CRC_OFFSET + 4] = struct.pack("<I", new_crc)
    return new_crc

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "rw/saves/proofs/geppetto/epilogue/laser-lenses_1/Profile_1.ob"
DEST_DIR = REPO_ROOT / "rw/saves/edits/lab/geppetto/laser-lenses_1/talent-slot6-to-twin-dummies__from-epilogue"
DEST = DEST_DIR / "Profile_1.ob"

# Talent record locator
TALENT_RECORD_TAG_GUID = bytes.fromhex("12000000bfe7f6604385cb4887f6b4b79f6812")

# Twin Dummies skill-controller GUID (from data/heroes/geppetto.yaml)
TWIN_DUMMIES_GUID = bytes.fromhex("33cdbac4ce86134da99bc59a19021b6a")
assert len(TWIN_DUMMIES_GUID) == 16

CLOSE_MARKER = b"\x22\x22\xbb\xaa"


def find_picks_count_offset(data: bytes, rec_off: int) -> tuple[int, int]:
    """Walk back from the run-state-record close marker to locate the picks count u32.

    Returns (picks_count_offset, count_value).
    """
    cursor = data.find(CLOSE_MARKER, rec_off)
    while cursor >= 0:
        if cursor < 20:
            cursor = data.find(CLOSE_MARKER, cursor + 4)
            continue
        pre = data[cursor - 20 : cursor]
        if pre[:8] == b"\x00" * 8 and pre[12:20] == b"\x00" * 8:
            f_val = struct.unpack_from("<f", pre, 8)[0]
            if 100.0 < f_val < 5000.0:
                picks_end = cursor - 20
                # Try N = 1..15 for the picks count.
                for n in range(1, 16):
                    count_off = picks_end - n * 16 - 4
                    if count_off <= rec_off:
                        continue
                    count = struct.unpack_from("<I", data, count_off)[0]
                    if count == n:
                        return count_off, n
        cursor = data.find(CLOSE_MARKER, cursor + 4)
    raise SystemExit("could not locate picks count via backward walk")


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"source not found: {SOURCE}")
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    data = bytearray(SOURCE.read_bytes())
    old_crc = get_crc(data)

    rec_off = data.find(TALENT_RECORD_TAG_GUID)
    if rec_off < 0:
        raise SystemExit("talent record not found in source")
    print(f"talent record @ 0x{rec_off:x}")

    count_off, count = find_picks_count_offset(data, rec_off)
    print(f"picks count u32 @ 0x{count_off:x}, N = {count}")
    if count < 6:
        raise SystemExit(f"source has only {count} picks; need ≥6 for slot 6 swap")

    slot_6_off = count_off + 4 + (6 - 1) * 16
    old_guid = bytes(data[slot_6_off : slot_6_off + 16])
    print(f"slot 6 GUID @ 0x{slot_6_off:x}")
    print(f"  old: {old_guid.hex()}")
    print(f"  new: {TWIN_DUMMIES_GUID.hex()}  (Twin Dummies)")

    data[slot_6_off : slot_6_off + 16] = TWIN_DUMMIES_GUID
    new_crc = recompute_crc(data)
    DEST.write_bytes(bytes(data))

    print(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    print(f"wrote {DEST}")


if __name__ == "__main__":
    main()
