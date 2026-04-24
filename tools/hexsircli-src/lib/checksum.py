"""Checksum algorithms and analysis logic."""

import zlib
from pathlib import Path

import click

from display_lib.output import header, info, success


def crc32_u32(data: bytes) -> int:
    """Compute CRC32 checksum as unsigned 32-bit integer."""
    return zlib.crc32(data) & 0xFFFFFFFF


def adler32_u32(data: bytes) -> int:
    """Compute Adler-32 checksum as unsigned 32-bit integer."""
    return zlib.adler32(data) & 0xFFFFFFFF


def sum32_u32(data: bytes) -> int:
    """Compute simple byte sum as unsigned 32-bit integer."""
    return sum(data) & 0xFFFFFFFF


def xor32_u32(data: bytes) -> int:
    """Compute XOR of all bytes as unsigned 32-bit integer."""
    value = 0
    for b in data:
        value ^= b
    return value & 0xFFFFFFFF


ALGORITHMS = {
    "crc32": crc32_u32,
    "adler32": adler32_u32,
    "sum32": sum32_u32,
    "xor32": xor32_u32,
}


def fmt_u32(value: int) -> str:
    """Format unsigned 32-bit integer as hex string."""
    return f"0x{value:08X}"


def fmt_bytes(data: bytes) -> str:
    """Format bytes as uppercase hex with spaces."""
    return data.hex(" ").upper()


def compute_algorithm_matches(stored: bytes, body: bytes) -> list[dict]:
    """Compute all algorithm results against stored checksum bytes."""
    stored_little = int.from_bytes(stored, "little")
    stored_big = int.from_bytes(stored, "big")

    results = []
    for name, func in ALGORITHMS.items():
        computed = func(body)
        results.append(
            {
                "algorithm": name,
                "stored_bytes": stored,
                "computed": computed,
                "stored_little": stored_little,
                "stored_big": stored_big,
                "match_little": computed == stored_little,
                "match_big": computed == stored_big,
            }
        )
    return results


def check_algorithms_at_beginning(data: bytes) -> list[dict]:
    """Check algorithms assuming 4-byte checksum at start of data."""
    if len(data) < 4:
        raise ValueError("Need at least 4 bytes to check beginning.")
    return compute_algorithm_matches(data[:4], data[4:])


def check_algorithms_at_end(data: bytes) -> list[dict]:
    """Check algorithms assuming 4-byte checksum at end of data."""
    if len(data) < 4:
        raise ValueError("Need at least 4 bytes to check end.")
    return compute_algorithm_matches(data[-4:], data[:-4])


def read_file_bytes(file_path: str) -> bytes:
    """Read file and return bytes."""
    try:
        data = Path(file_path).read_bytes()
    except OSError as exc:
        raise click.ClickException(f"Error reading file: {exc}") from exc

    if len(data) < 4:
        raise click.ClickException("File must be at least 4 bytes long.")

    return data


def validate_offset(offset: int, data_len: int, name: str = "offset") -> None:
    """Validate offset is within file bounds."""
    if offset < 0:
        raise click.ClickException(f"{name} cannot be negative.")
    if offset >= data_len:
        raise click.ClickException(
            f"{name} is larger than or equal to file size ({data_len} bytes)."
        )


def print_result_block(title: str, results: list[dict]) -> None:
    """Print a block of checksum results."""
    if not results:
        return

    first = results[0]
    print(f"\n[{title}]")
    print(f"stored bytes      : {fmt_bytes(first['stored_bytes'])}")
    print(f"stored as little  : {fmt_u32(first['stored_little'])}")
    print(f"stored as big     : {fmt_u32(first['stored_big'])}")

    for result in results:
        print(
            f"{result['algorithm']:<14}"
            f"computed={fmt_u32(result['computed'])}  "
            f"little={result['match_little']}  "
            f"big={result['match_big']}"
        )


def collect_matches(results: list[dict], location: str) -> list[str]:
    """Collect match descriptions from results."""
    matches = []
    for r in results:
        if r["match_little"]:
            matches.append(f"{r['algorithm']} at {location} (little-endian)")
        if r["match_big"]:
            matches.append(f"{r['algorithm']} at {location} (big-endian)")
    return matches


def analyze_region(data: bytes, label: str) -> list[tuple[str, str]]:
    """Analyze a region of data for checksums at beginning and end.

    Returns list of (label, match_description) tuples for any matches found.
    Prints inline success message for each match.
    """
    header(f"{label} ({len(data)} bytes)")

    if len(data) < 4:
        info("Region too small to analyze.")
        return []

    begin_results = check_algorithms_at_beginning(data)
    end_results = check_algorithms_at_end(data)

    print_result_block("4-byte checksum at beginning", begin_results)
    print_result_block("4-byte checksum at end", end_results)

    all_matches = []
    all_matches.extend(collect_matches(begin_results, "beginning"))
    all_matches.extend(collect_matches(end_results, "end"))

    print()
    if all_matches:
        for match in all_matches:
            success(f"Match: {match}")
    else:
        info("No matches")

    return [(label, m) for m in all_matches]


def print_summary(all_matches: list[tuple[str, str]]) -> None:
    """Print summary of all matches found."""
    print()
    header("Summary")
    if all_matches:
        info(f"Found {len(all_matches)} match(es):")
        for label, match in all_matches:
            success(f"  {label}: {match}")
    else:
        info("No matches found")
