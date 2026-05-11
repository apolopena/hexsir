"""Environment variable handling for hexsir."""

import os

import click


def parse_ckspec(raw: str) -> dict[str, str]:
    """Parse HEXSIR_CKSPEC format: offset=X,length=Y,value=Z."""
    result = {}

    for part in raw.split(","):
        if "=" not in part:
            raise click.UsageError(f"Invalid HEXSIR_CKSPEC part: {part}")

        key, value = part.split("=", 1)
        result[key.strip()] = value.strip()

    missing = {"offset", "length", "value"} - result.keys()
    if missing:
        raise click.UsageError(
            f"HEXSIR_CKSPEC missing required key(s): {', '.join(sorted(missing))}"
        )

    return result


def resolve_ckspec(
    offset: int | None,
    length: int | None,
    value: str | None,
) -> tuple[int, int, bytes]:
    """Resolve checksum spec from flags or HEXSIR_CKSPEC env var.

    Args:
        offset: Checksum offset from flag, or None.
        length: Checksum length from flag, or None.
        value: Checksum value hex string from flag, or None.

    Returns:
        Tuple of (offset, length, value_bytes).

    Raises:
        click.UsageError: If required values are missing or invalid.
    """
    spec: dict[str, str] = {}

    raw = os.getenv("HEXSIR_CKSPEC")
    if raw:
        spec.update(parse_ckspec(raw))

    if offset is not None:
        spec["offset"] = str(offset)
    if length is not None:
        spec["length"] = str(length)
    if value is not None:
        spec["value"] = value

    missing = {"offset", "length", "value"} - spec.keys()
    if missing:
        raise click.UsageError(
            "Missing checksum spec. Provide flags or set HEXSIR_CKSPEC."
        )

    checksum_offset = int(spec["offset"], 0)
    checksum_length = int(spec["length"], 0)
    checksum_value = bytes.fromhex(spec["value"])

    if len(checksum_value) != checksum_length:
        raise click.UsageError("Checksum value length mismatch.")

    return checksum_offset, checksum_length, checksum_value


def choose_safe_offset(
    data_len: int, checksum_offset: int, checksum_length: int
) -> int:
    """Find a byte offset in the body region for mutation.

    Args:
        data_len: Total length of data.
        checksum_offset: Start of checksum region.
        checksum_length: Length of checksum region.

    Returns:
        First byte offset in the body (after checksum region).

    Raises:
        click.UsageError: If no safe offset exists.
    """
    body_start = checksum_offset + checksum_length

    if body_start < data_len:
        return body_start

    raise click.UsageError("No safe offset found.")
