"""Tests for lib/encoding.py."""

import pytest

from lib.encoding import (
    DELIMITER_PATTERNS,
    SUPPORTED_ENCODINGS,
    build_key_patterns,
    encode_delimiter,
    encode_text,
)


def test_supported_encodings():
    """SUPPORTED_ENCODINGS contains expected values."""
    assert "ascii" in SUPPORTED_ENCODINGS
    assert "utf16le" in SUPPORTED_ENCODINGS


def test_delimiter_patterns():
    """DELIMITER_PATTERNS contains expected patterns."""
    assert "=" in DELIMITER_PATTERNS
    assert ":" in DELIMITER_PATTERNS
    assert "\x00" in DELIMITER_PATTERNS


def test_encode_text_ascii():
    """Encodes text as ASCII."""
    result = encode_text("hello", "ascii")
    assert result == b"hello"


def test_encode_text_utf16le():
    """Encodes text as UTF-16LE."""
    result = encode_text("hello", "utf16le")
    assert result == "hello".encode("utf-16le")


def test_encode_text_unsupported():
    """Raises error for unsupported encoding."""
    with pytest.raises(Exception) as exc_info:
        encode_text("hello", "unsupported")
    assert "Unsupported encoding" in str(exc_info.value)


def test_encode_delimiter_ascii():
    """Encodes delimiter as ASCII."""
    result = encode_delimiter("=", "ascii")
    assert result == b"="


def test_encode_delimiter_null():
    """Encodes null delimiter using latin1."""
    result = encode_delimiter("\x00", "ascii")
    assert result == b"\x00"


def test_encode_delimiter_double_null():
    """Encodes double null using latin1."""
    result = encode_delimiter("\x00\x00", "ascii")
    assert result == b"\x00\x00"


def test_build_key_patterns():
    """Builds patterns for all supported encodings."""
    patterns = build_key_patterns("test")

    assert len(patterns) == len(SUPPORTED_ENCODINGS)

    encodings = [enc for enc, _ in patterns]
    assert "ascii" in encodings
    assert "utf16le" in encodings

    for enc, pattern in patterns:
        assert isinstance(pattern, bytes)
