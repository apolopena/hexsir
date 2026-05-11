"""Display helpers for hexsir output."""

from display_lib.output import header, info, success


def fmt_u32(value: int) -> str:
    """Format unsigned 32-bit integer as hex string."""
    return f"0x{value:08X}"


def fmt_bytes(data: bytes) -> str:
    """Format bytes as uppercase hex with spaces."""
    return data.hex(" ").upper()


def print_result_block(title: str, entries: list[tuple[str, str]]) -> None:
    """Print a titled block of key-value pairs with aligned keys."""
    header(title)
    if not entries:
        return
    max_key_len = max(len(k) for k, v in entries)
    for key, value in entries:
        info(f"{key:<{max_key_len}}: {value}")


def print_checksum_results(title: str, results: list[dict]) -> None:
    """Print checksum analysis results in standardized block format."""
    if not results:
        return
    first = results[0]
    entries = [
        ("stored bytes", fmt_bytes(first["stored_bytes"])),
        ("stored as little", fmt_u32(first["stored_little"])),
        ("stored as big", fmt_u32(first["stored_big"])),
    ]
    for r in results:
        entries.append(
            (
                r["algorithm"],
                f"computed={fmt_u32(r['computed'])}  "
                f"little={r['match_little']}  "
                f"big={r['match_big']}",
            )
        )
    print_result_block(title, entries)


def collect_matches(results: list[dict], location: str) -> list[str]:
    """Collect match descriptions from checksum results."""
    matches = []
    for r in results:
        if r["match_little"]:
            matches.append(f"{r['algorithm']} at {location} (little-endian)")
        if r["match_big"]:
            matches.append(f"{r['algorithm']} at {location} (big-endian)")
    return matches


def print_match_summary(all_matches: list[tuple[str, str]]) -> None:
    """Print summary of all matches found."""
    print()
    header("Summary")
    if all_matches:
        info(f"Found {len(all_matches)} match(es):")
        for label, match in all_matches:
            success(f"  {label}: {match}")
    else:
        info("No matches found")
