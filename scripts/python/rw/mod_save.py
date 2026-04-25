#!/usr/bin/env python3
"""Modify Ravenswatch save file values."""

import argparse
import struct
import zlib
from pathlib import Path


# Known GUIDs for values (value follows immediately after GUID)
KNOWN_GUIDS = {
    "Level": bytes.fromhex("b5317efe6f4a95737325675793e600"),  # WORKS! Max ~15
    "ProfileDreamShards": bytes.fromhex("b43eeb58d162fa41acef99d128f2cb"),  # profile-level (not run)
}


def read_save(path: Path) -> bytearray:
    """Read save file into mutable bytearray."""
    return bytearray(path.read_bytes())


def get_crc(data: bytes) -> int:
    """Get current CRC32 from offset 12."""
    return struct.unpack("<I", data[12:16])[0]


def compute_crc(data: bytes) -> int:
    """Compute CRC32 of body (offset 16 onwards)."""
    return zlib.crc32(data[16:]) & 0xFFFFFFFF


def update_crc(data: bytearray) -> None:
    """Recalculate and write CRC32."""
    new_crc = compute_crc(data)
    data[12:16] = struct.pack("<I", new_crc)


def get_int32(data: bytes, offset: int) -> int:
    """Read int32 LE at offset."""
    return struct.unpack("<I", data[offset : offset + 4])[0]


def set_int32(data: bytearray, offset: int, value: int) -> None:
    """Write int32 LE at offset."""
    data[offset : offset + 4] = struct.pack("<I", value)


def find_by_guid(data: bytes, guid: bytes) -> int | None:
    """Find value offset by GUID. Returns offset of value (after GUID)."""
    pos = data.find(guid)
    if pos == -1:
        return None
    return pos + len(guid)


def show_known_values(data: bytes) -> None:
    """Display all known values found by GUID."""
    print("Known values (by GUID):")
    for name, guid in KNOWN_GUIDS.items():
        offset = find_by_guid(data, guid)
        if offset is not None:
            val = get_int32(data, offset)
            print(f"  {name}: {val} (at 0x{offset:x})")
        else:
            print(f"  {name}: GUID not found")


def main():
    parser = argparse.ArgumentParser(description="Modify Ravenswatch save values")
    parser.add_argument("file", help="Save file path")
    parser.add_argument("--output", "-o", help="Output file (default: <input>.mod.ob)")
    parser.add_argument("--show", action="store_true", help="Show known values without modifying")
    parser.add_argument(
        "--set",
        nargs=2,
        metavar=("NAME_OR_OFFSET", "VALUE"),
        action="append",
        help="Set value by name or offset. Can be repeated.",
    )

    args = parser.parse_args()

    input_path = Path(args.file)
    data = read_save(input_path)

    print(f"File: {input_path}")
    print(f"Size: {len(data)} bytes")
    print(f"CRC32: 0x{get_crc(data):08X}")
    print()

    if args.show:
        show_known_values(data)
        return

    if not args.set:
        parser.error("Must specify --show or --set")

    # Apply modifications
    print("Modifications:")
    for target, value_str in args.set:
        value = int(value_str)

        # Check if target is a known name
        if target in KNOWN_GUIDS:
            offset = find_by_guid(data, KNOWN_GUIDS[target])
            if offset is None:
                print(f"  {target}: GUID not found, skipping")
                continue
            name = target
        else:
            # Treat as hex/decimal offset
            offset = int(target, 0)
            name = f"0x{offset:x}"

        old_value = get_int32(data, offset)
        set_int32(data, offset, value)
        print(f"  {name}: {old_value} -> {value}")

    # Update CRC
    old_crc = get_crc(data)
    update_crc(data)
    new_crc = get_crc(data)
    print(f"\nCRC32: 0x{old_crc:08X} -> 0x{new_crc:08X}")

    # Write output
    output_path = Path(args.output) if args.output else input_path.with_suffix(".mod.ob")
    output_path.write_bytes(data)
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
