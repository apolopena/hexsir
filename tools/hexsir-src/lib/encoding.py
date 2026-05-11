"""Text encoding helpers for binary pattern matching."""

import click

SUPPORTED_ENCODINGS = ("ascii", "utf16le")

DELIMITER_PATTERNS = [
    "=",
    " = ",
    ":",
    " : ",
    " ",
    "\t",
    "\x00",
    "\x00\x00",
]


def encode_text(value: str, encoding: str) -> bytes:
    """Encode text string to bytes using specified encoding."""
    if encoding == "ascii":
        return value.encode("ascii")
    if encoding == "utf16le":
        return value.encode("utf-16le")
    raise click.UsageError(f"Unsupported encoding: {encoding}")


def encode_delimiter(raw: str, encoding: str) -> bytes:
    """Encode delimiter pattern to bytes, handling null bytes specially."""
    if raw.startswith("\x00"):
        return raw.encode("latin1")
    return encode_text(raw, encoding)


def build_key_patterns(key: str) -> list[tuple[str, bytes]]:
    """Build list of (encoding, pattern) tuples for a key."""
    return [(enc, encode_text(key, enc)) for enc in SUPPORTED_ENCODINGS]
