"""Inspect the talent picks-block layout across chapter 2 / 3 / epilogue proofs.

Goal: decode the storage layout for slot counts != 5. Chapter 2 has count=5 (verified);
chapter 3 and epilogue have higher counts (unverified — `rw/key-findings/talent-records.md`
flags this as the open dig).

For each proof:
  1. Locate the tag=0x12 talent record by its 15-byte GUID.
  2. Find the `00 00 00 00 NN 00 00 00` count sentinel (any NN).
  3. Dump bytes from sentinel to sentinel + 0x100 with annotation.
  4. Test the linear-append hypothesis: `picks_start = sentinel + 8`, body = NN × 16-byte
     GUIDs, trailing block (8-byte pad / float / 4-byte pad / 4-byte close marker).

Usage:
  uv run python rw/scripts/inspect_picks_block.py
"""

import sys
import struct
from pathlib import Path

# Stable 15-byte talent record type GUID (per talent-records.md).
TALENT_RECORD_GUID = bytes.fromhex("bfe7f6604385cb4887f6b4b79f6812")
# Tag prefix for the run-state record family.
TAG_PREFIX = b"\x12\x00\x00\x00"


PROOFS = [
    ("chapter2 / laser-lenses_1", "rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob"),
    ("chapter3 / laser_lenses_1", "rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob"),
    ("epilogue / laser-lenses_1", "rw/saves/proofs/geppetto/epilogue/laser-lenses_1/Profile_1.ob"),
]


def find_talent_record(data: bytes) -> int:
    needle = TAG_PREFIX + TALENT_RECORD_GUID
    pos = data.find(needle)
    if pos < 0:
        raise SystemExit("talent record not found")
    return pos


def find_count_sentinel(data: bytes, start: int) -> list[tuple[int, int]]:
    """Find ALL `00 00 00 00 NN 00 00 00` candidates after `start` where NN ∈ [0, 10].

    Returns list of (sentinel_offset, count_value). Caller picks the right one.
    """
    out: list[tuple[int, int]] = []
    i = start
    while i + 8 <= len(data):
        if (
            data[i] == 0 and data[i + 1] == 0 and data[i + 2] == 0 and data[i + 3] == 0
            and data[i + 5] == 0 and data[i + 6] == 0 and data[i + 7] == 0
        ):
            count = data[i + 4]
            if 0 <= count <= 10:
                out.append((i, count))
        i += 1
    return out


def hex_block(data: bytes, off: int, length: int, label: str) -> None:
    print(f"  {label} @ 0x{off:x} ({length} bytes):")
    for row in range(0, length, 16):
        chunk = data[off + row : off + row + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        ascii_repr = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"    {off + row:08x}  {hexs:<48s}  {ascii_repr}")


def inspect(label: str, path: str) -> None:
    fpath = Path(path)
    if not fpath.exists():
        print(f"\n=== {label} ===\n  MISSING: {path}")
        return

    data = fpath.read_bytes()
    print(f"\n=== {label} ===")
    print(f"  file: {path}")
    print(f"  size: {len(data)} bytes")

    rec_off = find_talent_record(data)
    print(f"  talent record (tag=0x12+GUID) @ 0x{rec_off:x}")

    candidates = find_count_sentinel(data, rec_off)
    print(f"  found {len(candidates)} sentinel candidates (count ∈ [0,10]) after 0x{rec_off:x}:")

    # Score each candidate: linear-append validity = trailing float in the 800-1500 range
    # (timing accumulator) at picks_end + 8. The right candidate should score uniquely.
    scored: list[tuple[int, int, float, str]] = []
    for off, count in candidates:
        picks_end = off + 8 + count * 16
        if picks_end + 16 > len(data):
            scored.append((off, count, 0.0, "OOB"))
            continue
        f = struct.unpack_from("<f", data, picks_end + 8)[0]
        plausible = "PLAUSIBLE" if 800.0 < f < 2000.0 else ""
        scored.append((off, count, f, plausible))

    for off, count, f, tag in scored[:20]:
        marker = "  ←" if tag == "PLAUSIBLE" else ""
        print(f"    @ 0x{off:08x}  count={count:3d}  trailing_float={f:>14.4f}  {tag}{marker}")

    plausible = [c for c in scored if c[3] == "PLAUSIBLE"]
    if not plausible:
        print(f"  NO PLAUSIBLE count=5-style sentinel — different layout. Walking back from close marker.")
        # Find the run-state-record close `22 22 bb aa` after the items array.
        # Per magical-objects.md the trailing block ends `[8 zero][float][8 zero][close]`.
        close = b"\x22\x22\xbb\xaa"
        c = data.find(close, rec_off)
        # Skip closes inside item records (they're 32-byte framed: marker+tag+guid+counter+close).
        # The run-state-record close is the LAST close before any new tag-prefix region.
        while c >= 0:
            # Look backward for the trailing [8 zero][float][8 zero] pattern just before this close.
            if c >= 20:
                pre = data[c - 20 : c]
                # 8 zero, 4-byte float, 8 zero
                if pre[:8] == b"\x00" * 8 and pre[12:20] == b"\x00" * 8:
                    f_val = struct.unpack_from("<f", pre, 8)[0]
                    if 100.0 < f_val < 5000.0:
                        # This is the run-state-record close. Walk back to find picks count.
                        scalar_off = c - 12
                        post_picks_pad_off = c - 20
                        print(f"  found run-state-record close @ 0x{c:08x}")
                        print(f"    trailing scalar (float) = {f_val:.4f} @ 0x{scalar_off:x}")
                        # The picks block is 16-byte GUIDs immediately before [8 zero][float][8 zero][close].
                        # Search backward for a u32 N followed by exactly N*16 bytes of (likely-non-zero)
                        # data ending at post_picks_pad_off. Try N = 1..15.
                        for n in range(1, 16):
                            count_off = post_picks_pad_off - n * 16 - 4
                            if count_off <= rec_off:
                                continue
                            count = struct.unpack_from("<I", data, count_off)[0]
                            if count != n:
                                continue
                            print(f"    candidate: count u32 = {n} @ 0x{count_off:x}, "
                                  f"picks block 0x{count_off + 4:x}..0x{post_picks_pad_off:x}")
                            # Show the bytes immediately before the count u32 (set-bonus tracker tail)
                            hex_block(data, max(rec_off, count_off - 32), 32, "32 bytes before count u32")
                            hex_block(data, count_off, 4 + n * 16 + 8 + 4 + 8 + 4, f"picks block + trailer (n={n})")
                            return
                        print(f"  could not back-fit a valid count u32 + N*16 picks block")
                        return
            c = data.find(close, c + 4)
        print(f"  no run-state-record close marker found in vicinity")
        return
    if len(plausible) > 1:
        print(f"  WARNING: {len(plausible)} plausible candidates — picking first")

    sent_off, count, f, _ = plausible[0]
    picks_start = sent_off + 8
    picks_end = picks_start + count * 16
    print()
    print(f"  SELECTED: sentinel @ 0x{sent_off:x}, count = {count}, "
          f"picks_block = {count * 16} bytes")
    print(f"  picks_start = 0x{picks_start:x}, picks_end = 0x{picks_end:x}")
    print(f"  trailing timing float = {f:.4f}")

    hex_block(data, sent_off, 8, "sentinel (8 bytes)")
    if count > 0:
        hex_block(data, picks_start, count * 16, f"picks block (count={count} × 16)")
    hex_block(data, picks_end, 32, "trailing 32 bytes")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for label, rel in PROOFS:
        inspect(label, str(repo_root / rel))


if __name__ == "__main__":
    main()
