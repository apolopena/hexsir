#!/usr/bin/env python3
"""Analyze Ravenswatch save file structure."""

import argparse
import re
import struct
from pathlib import Path


def find_markers(data: bytes, marker: bytes = b"\x11\x11\xbb\xaa") -> list[int]:
    """Find all occurrences of a marker pattern."""
    positions = []
    start = 0
    while True:
        pos = data.find(marker, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1
    return positions


def dump_context(data: bytes, offset: int, before: int = 8, after: int = 24) -> str:
    """Dump hex context around an offset."""
    start = max(0, offset - before)
    end = min(len(data), offset + after)

    chunk = data[start:end]
    hex_str = chunk.hex(" ")

    # Mark the target offset
    marker_pos = offset - start

    return f"0x{offset:08x}: {hex_str}"


def extract_strings(data: bytes, min_length: int = 4) -> list[tuple[int, str]]:
    """Extract readable ASCII strings with their offsets."""
    pattern = rb"[\x20-\x7e]{" + str(min_length).encode() + rb",}"
    strings = []

    for match in re.finditer(pattern, data):
        strings.append((match.start(), match.group().decode("ascii")))

    return strings


def search_value(data: bytes, value: int) -> dict[str, list[int]]:
    """Search for a value in various encodings."""
    results = {}

    # int8 (if value fits)
    if 0 <= value <= 255:
        positions = []
        for i, b in enumerate(data):
            if b == value:
                positions.append(i)
        if positions:
            results["int8"] = positions

    # int16 little-endian
    if 0 <= value <= 65535:
        needle = struct.pack("<H", value)
        positions = []
        start = 0
        while True:
            pos = data.find(needle, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        if positions:
            results["int16_le"] = positions

    # int32 little-endian
    if 0 <= value <= 0xFFFFFFFF:
        needle = struct.pack("<I", value)
        positions = []
        start = 0
        while True:
            pos = data.find(needle, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        if positions:
            results["int32_le"] = positions

    # float32
    try:
        needle = struct.pack("<f", float(value))
        positions = []
        start = 0
        while True:
            pos = data.find(needle, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        if positions:
            results["float32"] = positions
    except (OverflowError, struct.error):
        pass

    return results


def analyze_after_marker(data: bytes, marker_pos: int) -> dict:
    """Analyze the bytes immediately after a marker."""
    after = data[marker_pos + 4 : marker_pos + 20]
    if len(after) < 4:
        return {}

    result = {
        "raw_hex": after[:16].hex(" "),
    }

    # Try interpreting first 4 bytes as length
    potential_len = struct.unpack("<I", after[:4])[0]
    if 0 < potential_len < 10000:
        result["potential_length"] = potential_len
        # Check if that many bytes exist after
        if marker_pos + 8 + potential_len <= len(data):
            result["length_plausible"] = True

    return result


def main():
    parser = argparse.ArgumentParser(description="Analyze Ravenswatch save file")
    parser.add_argument("file", help="Path to save file")
    parser.add_argument("--markers", action="store_true", help="Find record markers")
    parser.add_argument("--strings", action="store_true", help="Extract strings")
    parser.add_argument("--search", type=int, nargs="+", metavar="VALUE",
                        help="Search for integer values")
    parser.add_argument("--all", action="store_true", help="Run all analyses")
    parser.add_argument("--min-string", type=int, default=6,
                        help="Minimum string length (default: 6)")
    parser.add_argument("--context", type=int, default=24,
                        help="Bytes of context after markers (default: 24)")

    args = parser.parse_args()

    data = Path(args.file).read_bytes()
    print(f"File size: {len(data)} bytes")
    print()

    if args.all or args.markers:
        print("=" * 60)
        print("RECORD MARKERS (1111bbaa)")
        print("=" * 60)
        markers = find_markers(data)
        print(f"Found {len(markers)} markers\n")

        for pos in markers:
            print(dump_context(data, pos, before=4, after=args.context))
            analysis = analyze_after_marker(data, pos)
            if analysis.get("potential_length"):
                plausible = "✓" if analysis.get("length_plausible") else "?"
                print(f"         ^ potential length: {analysis['potential_length']} {plausible}")
            print()

    if args.all or args.strings:
        print("=" * 60)
        print(f"STRINGS (min length: {args.min_string})")
        print("=" * 60)
        strings = extract_strings(data, min_length=args.min_string)
        print(f"Found {len(strings)} strings\n")

        for offset, s in strings:
            # Truncate long strings for display
            display = s if len(s) <= 60 else s[:57] + "..."
            print(f"0x{offset:08x}: {display}")
        print()

    if args.search:
        print("=" * 60)
        print("VALUE SEARCH")
        print("=" * 60)

        for value in args.search:
            print(f"\nSearching for {value}:")
            results = search_value(data, value)
            if not results:
                print("  No matches")
            else:
                for encoding, positions in results.items():
                    if len(positions) <= 10:
                        pos_str = ", ".join(f"0x{p:x}" for p in positions)
                    else:
                        pos_str = ", ".join(f"0x{p:x}" for p in positions[:5])
                        pos_str += f" ... ({len(positions)} total)"
                    print(f"  {encoding}: {pos_str}")


if __name__ == "__main__":
    main()
