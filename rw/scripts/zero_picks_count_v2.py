"""Patch picks-block count u32 from 5 to 0 AND delete the 80 bytes of GUIDs.

Layout around the picks block:
  ... [stuff] [sentinel 8 bytes: 00 00 00 00 05 00 00 00] [80 bytes: 5 GUIDs]
  [16 bytes trailing fields] [2222bbaa frame end] ...

Patch: change count u32 5 -> 0 AND remove the 80 bytes of GUIDs. File shrinks
by 80 bytes. CRC recomputed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "rerw-src"))

from lib.save_edit import recompute_crc, get_crc

SENTINEL_COUNT5 = bytes.fromhex("0000000005000000")
GUIDS_LEN = 5 * 16  # 80 bytes


def main(target: Path) -> None:
    data = bytearray(target.read_bytes())
    old_crc = get_crc(data)
    old_len = len(data)

    record_guid = bytes.fromhex("bfe7f6604385cb4887f6b4b79f6812")
    needle = b"\x12\x00\x00\x00" + record_guid
    rec = data.find(needle)
    if rec < 0:
        raise SystemExit("talent record GUID not found")
    pos = data.find(SENTINEL_COUNT5, rec)
    if pos < 0:
        raise SystemExit("count=5 sentinel not found after talent record")

    # 1. Patch count u32 (last 4 bytes of 8-byte sentinel) from 5 to 0.
    count_off = pos + 4
    data[count_off : count_off + 4] = b"\x00\x00\x00\x00"
    print(f"count u32 @ 0x{count_off:x}: 5 -> 0")

    # 2. Delete the 80 bytes of GUIDs immediately after the sentinel.
    picks_start = pos + 8
    del data[picks_start : picks_start + GUIDS_LEN]
    print(f"deleted {GUIDS_LEN} bytes of GUIDs @ 0x{picks_start:x}")

    new_crc = recompute_crc(data)
    target.write_bytes(bytes(data))
    print(f"file size: {old_len} -> {len(data)} bytes")
    print(f"CRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")
    print(f"wrote {target}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
