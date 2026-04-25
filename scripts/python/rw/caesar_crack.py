#!/usr/bin/env python3
"""Break Caesar cipher on game data files."""

import argparse
import string
from pathlib import Path
from collections import Counter


def caesar_shift(data: bytes, shift: int) -> bytes:
    """Apply Caesar shift to all bytes."""
    return bytes((b + shift) % 256 for b in data)


def score_english(data: bytes) -> float:
    """Score how likely data contains English text (higher = more likely)."""
    # Common English letter frequencies
    english_freq = {
        'e': 12.7, 't': 9.1, 'a': 8.2, 'o': 7.5, 'i': 7.0,
        'n': 6.7, 's': 6.3, 'h': 6.1, 'r': 6.0, 'd': 4.3,
        'l': 4.0, 'c': 2.8, 'u': 2.8, 'm': 2.4, 'w': 2.4,
        'f': 2.2, 'g': 2.0, 'y': 2.0, 'p': 1.9, 'b': 1.5,
    }

    # Count printable ASCII
    printable = sum(1 for b in data if 32 <= b < 127)
    if len(data) == 0:
        return 0

    printable_ratio = printable / len(data)

    # Count letter frequencies
    letters = [chr(b).lower() for b in data if chr(b).lower() in string.ascii_lowercase]
    if not letters:
        return printable_ratio * 10

    freq = Counter(letters)
    total = len(letters)

    # Compare to English frequencies
    score = 0
    for letter, expected in english_freq.items():
        actual = (freq.get(letter, 0) / total) * 100
        score += min(actual, expected)  # Reward matches

    return score + (printable_ratio * 20)


def find_strings(data: bytes, min_len: int = 6) -> list[tuple[int, str]]:
    """Find printable ASCII strings in data."""
    strings = []
    current = []
    start = 0

    for i, b in enumerate(data):
        if 32 <= b < 127:
            if not current:
                start = i
            current.append(chr(b))
        else:
            if len(current) >= min_len:
                strings.append((start, ''.join(current)))
            current = []

    if len(current) >= min_len:
        strings.append((start, ''.join(current)))

    return strings


def try_xor(data: bytes, key: int) -> bytes:
    """XOR all bytes with a single-byte key."""
    return bytes(b ^ key for b in data)


def main():
    parser = argparse.ArgumentParser(description="Break Caesar/XOR cipher on game files")
    parser.add_argument("file", help="File to analyze")
    parser.add_argument("--offset", type=lambda x: int(x, 0), default=0, help="Start offset")
    parser.add_argument("--length", type=int, default=4096, help="Bytes to analyze")
    parser.add_argument("--shift", type=int, help="Try specific Caesar shift")
    parser.add_argument("--xor", type=int, help="Try specific XOR key")
    parser.add_argument("--brute", action="store_true", help="Try all shifts 0-255")
    parser.add_argument("--strings", action="store_true", help="Just find strings in original")
    parser.add_argument("--out", help="Write decoded output to file")

    args = parser.parse_args()

    path = Path(args.file)
    with open(path, 'rb') as f:
        f.seek(args.offset)
        data = f.read(args.length)

    print(f"File: {path}")
    print(f"Analyzing {len(data)} bytes from offset 0x{args.offset:x}")
    print()

    if args.strings:
        print("Strings found in original:")
        for offset, s in find_strings(data, min_len=4):
            print(f"  0x{args.offset + offset:04x}: {s}")
        return

    if args.shift is not None:
        decoded = caesar_shift(data, args.shift)
        print(f"Caesar shift {args.shift}:")
        print(f"  Score: {score_english(decoded):.2f}")
        print(f"  Strings: {find_strings(decoded)[:5]}")
        if args.out:
            Path(args.out).write_bytes(decoded)
            print(f"  Written to: {args.out}")
        return

    if args.xor is not None:
        decoded = try_xor(data, args.xor)
        print(f"XOR key 0x{args.xor:02x}:")
        print(f"  Score: {score_english(decoded):.2f}")
        print(f"  Strings: {find_strings(decoded)[:5]}")
        if args.out:
            Path(args.out).write_bytes(decoded)
            print(f"  Written to: {args.out}")
        return

    if args.brute:
        print("Brute forcing all Caesar shifts (0-255)...")
        results = []
        for shift in range(256):
            decoded = caesar_shift(data, shift)
            score = score_english(decoded)
            strings = find_strings(decoded, min_len=6)
            results.append((score, shift, len(strings), strings[:3]))

        results.sort(reverse=True)
        print("\nTop 10 Caesar shifts:")
        for score, shift, num_strings, sample in results[:10]:
            print(f"  Shift {shift:3d}: score={score:.1f}, strings={num_strings}, sample={sample[:2]}")

        print("\nBrute forcing all XOR keys (0-255)...")
        results = []
        for key in range(256):
            decoded = try_xor(data, key)
            score = score_english(decoded)
            strings = find_strings(decoded, min_len=6)
            results.append((score, key, len(strings), strings[:3]))

        results.sort(reverse=True)
        print("\nTop 10 XOR keys:")
        for score, key, num_strings, sample in results[:10]:
            print(f"  XOR 0x{key:02x}: score={score:.1f}, strings={num_strings}, sample={sample[:2]}")
        return

    # Default: show original analysis
    print("Original data analysis:")
    print(f"  Score: {score_english(data):.2f}")
    strings = find_strings(data, min_len=4)
    print(f"  Strings found: {len(strings)}")
    for offset, s in strings[:20]:
        print(f"    0x{args.offset + offset:04x}: {s}")

    print("\nUse --brute to try all Caesar/XOR shifts")
    print("Use --shift N or --xor N to try a specific key")


if __name__ == "__main__":
    main()
