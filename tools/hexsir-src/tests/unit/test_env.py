"""Tests for lib/env.py."""

import pytest

from lib.env import choose_safe_offset, parse_ckspec, resolve_ckspec


def test_parse_ckspec_valid():
    """Parses valid CKSPEC string."""
    result = parse_ckspec("offset=0,length=4,value=DEADBEEF")

    assert result["offset"] == "0"
    assert result["length"] == "4"
    assert result["value"] == "DEADBEEF"


def test_parse_ckspec_with_spaces():
    """Handles spaces in CKSPEC values."""
    result = parse_ckspec("offset = 10, length = 4, value = BEEF")

    assert result["offset"] == "10"
    assert result["length"] == "4"
    assert result["value"] == "BEEF"


def test_parse_ckspec_hex_offset():
    """Accepts hex offset in CKSPEC."""
    result = parse_ckspec("offset=0x10,length=4,value=DEADBEEF")
    assert result["offset"] == "0x10"


def test_parse_ckspec_missing_key():
    """Raises error for missing required key."""
    with pytest.raises(Exception) as exc_info:
        parse_ckspec("offset=0,length=4")
    assert "missing required key" in str(exc_info.value)


def test_parse_ckspec_invalid_format():
    """Raises error for invalid format."""
    with pytest.raises(Exception) as exc_info:
        parse_ckspec("invalid")
    assert "Invalid HEXSIR_CKSPEC part" in str(exc_info.value)


def test_resolve_ckspec_from_flags():
    """Resolves CKSPEC from flags."""
    offset, length, value = resolve_ckspec(
        offset=16,
        length=4,
        value="DEADBEEF",
    )

    assert offset == 16
    assert length == 4
    assert value == bytes.fromhex("DEADBEEF")


def test_resolve_ckspec_from_env(monkeypatch):
    """Resolves CKSPEC from environment variable."""
    monkeypatch.setenv("HEXSIR_CKSPEC", "offset=0,length=4,value=DEADBEEF")

    offset, length, value = resolve_ckspec(None, None, None)

    assert offset == 0
    assert length == 4
    assert value == bytes.fromhex("DEADBEEF")


def test_resolve_ckspec_flags_override_env(monkeypatch):
    """Flags override environment variable."""
    monkeypatch.setenv("HEXSIR_CKSPEC", "offset=0,length=4,value=00000000")

    offset, length, value = resolve_ckspec(
        offset=16,
        length=None,
        value="DEADBEEF",
    )

    assert offset == 16
    assert length == 4
    assert value == bytes.fromhex("DEADBEEF")


def test_resolve_ckspec_missing():
    """Raises error when CKSPEC not provided."""
    with pytest.raises(Exception) as exc_info:
        resolve_ckspec(None, None, None)
    assert "Missing checksum spec" in str(exc_info.value)


def test_resolve_ckspec_length_mismatch():
    """Raises error for value/length mismatch."""
    with pytest.raises(Exception) as exc_info:
        resolve_ckspec(offset=0, length=2, value="DEADBEEF")
    assert "length mismatch" in str(exc_info.value)


def test_choose_safe_offset_in_body():
    """Chooses first byte in body (after checksum region)."""
    offset = choose_safe_offset(data_len=10, checksum_offset=4, checksum_length=4)
    assert offset == 8


def test_choose_safe_offset_after_checksum():
    """Chooses offset after checksum when checksum at start."""
    offset = choose_safe_offset(data_len=10, checksum_offset=0, checksum_length=4)
    assert offset == 4


def test_choose_safe_offset_no_room():
    """Raises error when no safe offset exists."""
    with pytest.raises(Exception) as exc_info:
        choose_safe_offset(data_len=4, checksum_offset=0, checksum_length=4)
    assert "No safe offset found" in str(exc_info.value)
