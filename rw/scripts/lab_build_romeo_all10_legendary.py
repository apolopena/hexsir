"""Lab build: Romeo Golden + slots 6-10 also stamped Legendary.

Test A2 — verifies that switching the rarity-array skip from value-based
(skip any cur==4) to index-based (skip only slot index 4 = ult) extends
Legendary coverage from slots 1-4 to slots 1-10 minus the ult.

Source: existing Romeo Golden
  rw/saves/edits/golden/romeo-ch1-level14-pickscount0-rarities-legendary__from-laser-lenses_1-proof/Profile_1.ob

Output: rw/saves/edits/lab/geppetto/laser-lenses_1/romeo-ch1-level14-pickscount0-all10-legendary__from-romeo-golden/Profile_1.ob

What this script does:
  Reads the existing Romeo Golden, locates the talent record, walks the
  10-entry per-slot rarity u32 array at record_off + 0x35..+0x5c, and
  writes 3 (Legendary) into every entry EXCEPT slot index 4 (the ult).
  This overrides the chapter-2 source's "uninitialized=4" sentinels in
  slots 5-9 (= user slots 6-10), which the existing all-talent-rarities
  CLI skipped due to its value-based filter.

Verification:
  Load the lab save in-game. Picker proposals at slots 6-10 should arrive
  stamped Legendary (gold border / Legendary card frame). Slot 5 ult pick
  is unchanged.
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
SOURCE = REPO_ROOT / "rw/saves/edits/golden/romeo-ch1-level14-pickscount0-rarities-legendary__from-laser-lenses_1-proof/Profile_1.ob"
DEST_DIR = REPO_ROOT / "rw/saves/edits/lab/geppetto/laser-lenses_1/romeo-ch1-level14-pickscount0-all10-legendary__from-romeo-golden"
DEST = DEST_DIR / "Profile_1.ob"

# Talent record locator
TALENT_RECORD_TAG_GUID = bytes.fromhex("12000000bfe7f6604385cb4887f6b4b79f6812")

# Rarity array within the talent record body
SLOT_RARITY_ARRAY_OFFSET = 0x35    # bytes from record's tag byte
SLOT_COUNT = 10                     # 10 u32 entries
ULT_SLOT_INDEX = 4                  # zero-indexed; user slot 5

# Rarity values
LEGENDARY = 3


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

    array_off = rec_off + SLOT_RARITY_ARRAY_OFFSET
    new_value_bytes = LEGENDARY.to_bytes(4, "little")

    print(f"per-slot rarity array @ 0x{array_off:x}..0x{array_off + SLOT_COUNT * 4:x}")
    print("  index | user-slot | old -> new")
    written = 0
    skipped = 0
    for i in range(SLOT_COUNT):
        slot_off = array_off + i * 4
        cur = int.from_bytes(data[slot_off : slot_off + 4], "little")
        user_slot = i + 1
        if i == ULT_SLOT_INDEX:
            print(f"   {i:>3}  |    {user_slot:>2}     | {cur} (ult) -> SKIP")
            skipped += 1
            continue
        data[slot_off : slot_off + 4] = new_value_bytes
        print(f"   {i:>3}  |    {user_slot:>2}     | {cur} -> {LEGENDARY}")
        written += 1

    print(f"\nwrote {written} entries, skipped {skipped} (ult slot)")
    new_crc = recompute_crc(data)
    DEST.write_bytes(bytes(data))

    print(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    print(f"wrote {DEST}")


if __name__ == "__main__":
    main()
