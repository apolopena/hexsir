"""Tests for lib/display.py."""

from lib.display import (
    collect_matches,
    fmt_bytes,
    fmt_u32,
    print_checksum_results,
    print_match_summary,
    print_result_block,
)


def test_fmt_u32():
    """Formats unsigned 32-bit integer as hex."""
    assert fmt_u32(0) == "0x00000000"
    assert fmt_u32(255) == "0x000000FF"
    assert fmt_u32(0xDEADBEEF) == "0xDEADBEEF"


def test_fmt_bytes():
    """Formats bytes as uppercase hex with spaces."""
    assert fmt_bytes(b"\x00\x01\x02") == "00 01 02"
    assert fmt_bytes(b"\xde\xad\xbe\xef") == "DE AD BE EF"


def test_print_result_block(capsys):
    """Prints titled block with aligned key-value pairs."""
    entries = [
        ("short", "value1"),
        ("longer key", "value2"),
    ]
    print_result_block("Test Block", entries)

    captured = capsys.readouterr()
    assert "Test Block" in captured.out
    assert "short     : value1" in captured.out
    assert "longer key: value2" in captured.out


def test_print_result_block_empty(capsys):
    """Prints header only for empty entries."""
    print_result_block("Empty Block", [])
    captured = capsys.readouterr()
    assert "Empty Block" in captured.out


def test_collect_matches():
    """Collects match descriptions from results."""
    results = [
        {"algorithm": "crc32", "match_little": True, "match_big": False},
        {"algorithm": "adler32", "match_little": False, "match_big": True},
        {"algorithm": "sum32", "match_little": False, "match_big": False},
    ]

    matches = collect_matches(results, "beginning")

    assert len(matches) == 2
    assert "crc32 at beginning (little-endian)" in matches
    assert "adler32 at beginning (big-endian)" in matches


def test_print_checksum_results(capsys):
    """Prints checksum results in block format."""
    results = [
        {
            "algorithm": "crc32",
            "stored_bytes": b"\x01\x02\x03\x04",
            "stored_little": 0x04030201,
            "stored_big": 0x01020304,
            "computed": 0x12345678,
            "match_little": False,
            "match_big": False,
        }
    ]

    print_checksum_results("Test Results", results)

    captured = capsys.readouterr()
    assert "Test Results" in captured.out
    assert "stored bytes" in captured.out
    assert "crc32" in captured.out


def test_print_match_summary_with_matches(capsys):
    """Prints summary with matches."""
    matches = [
        ("region1", "crc32 at beginning (little-endian)"),
        ("region2", "adler32 at end (big-endian)"),
    ]

    print_match_summary(matches)

    captured = capsys.readouterr()
    assert "Summary" in captured.out
    assert "Found 2 match(es)" in captured.out


def test_print_match_summary_no_matches(capsys):
    """Prints summary with no matches."""
    print_match_summary([])

    captured = capsys.readouterr()
    assert "Summary" in captured.out
    assert "No matches found" in captured.out
