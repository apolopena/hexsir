"""Type codec for memory values used by rs read / write / watch.

Centralizes the supported type list, byte sizes, struct formats, and
encode/decode helpers so command code stays small. All multi-byte types
are little-endian (matches x86_64 and OEngine's on-disk format).
"""

import struct

# Per-type spec: (size in bytes, struct format string, or None for special-cased)
TYPE_SPECS: dict[str, dict] = {
    "hex": {"size": None, "fmt": None},
    "int32": {"size": 4, "fmt": "<i"},
    "uint32": {"size": 4, "fmt": "<I"},
    "int64": {"size": 8, "fmt": "<q"},
    "uint64": {"size": 8, "fmt": "<Q"},
    "float32": {"size": 4, "fmt": "<f"},
    "float64": {"size": 8, "fmt": "<d"},
    "bool": {"size": 1, "fmt": None},
}

TYPE_NAMES = list(TYPE_SPECS.keys())


def parse_addr(addr_str: str) -> int:
    """Parse an address string. Accepts ``0x...`` hex or plain decimal."""
    s = addr_str.strip().lower()
    if s.startswith("0x"):
        return int(s, 16)
    return int(s, 10)


def default_length(type_name: str, explicit: int | None) -> int:
    """Resolve read length: explicit override wins, else the type's natural size.

    For ``hex`` (variable-length) without an explicit length, defaults to 4.
    """
    if explicit is not None:
        return explicit
    spec = TYPE_SPECS[type_name]
    if spec["size"] is not None:
        return spec["size"]
    return 4


def decode(raw: bytes, type_name: str) -> object:
    """Decode raw bytes as ``type_name``. ``hex`` returns the hex string."""
    spec = TYPE_SPECS[type_name]
    if type_name == "hex":
        return raw.hex()
    if type_name == "bool":
        if len(raw) != 1:
            raise ValueError(f"bool requires 1 byte, got {len(raw)}")
        return raw[0] != 0
    expected = spec["size"]
    if len(raw) != expected:
        raise ValueError(f"{type_name} requires {expected} bytes, got {len(raw)}")
    return struct.unpack(spec["fmt"], raw)[0]


def format_value(value: object, type_name: str) -> str:
    """Format a decoded value for human-readable display."""
    if type_name == "hex":
        return str(value)
    if type_name == "bool":
        return "true" if value else "false"
    if type_name in ("float32", "float64"):
        return repr(value)
    return str(value)


def encode(value_str: str, type_name: str) -> bytes:
    """Encode a CLI string ``value_str`` as bytes for writing.

    Integer types accept decimal or ``0x...`` hex. ``hex`` accepts an
    even-length hex string with optional ``0x`` prefix and spaces.
    ``bool`` accepts 0/1/true/false (case-insensitive).
    """
    spec = TYPE_SPECS[type_name]
    if type_name == "hex":
        clean = value_str.replace(" ", "").lower()
        if clean.startswith("0x"):
            clean = clean[2:]
        if len(clean) % 2 != 0:
            raise ValueError(f"hex value must be even-length, got {len(clean)} chars")
        return bytes.fromhex(clean)
    if type_name == "bool":
        v = value_str.strip().lower()
        if v in ("1", "true", "t", "yes", "y"):
            return b"\x01"
        if v in ("0", "false", "f", "no", "n"):
            return b"\x00"
        raise ValueError(f"bool requires 0/1/true/false, got {value_str!r}")
    if type_name in ("float32", "float64"):
        return struct.pack(spec["fmt"], float(value_str))
    if value_str.strip().lower().startswith("0x"):
        n = int(value_str, 16)
    else:
        n = int(value_str, 10)
    return struct.pack(spec["fmt"], n)
