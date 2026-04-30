"""Per-class schemas for the oEngine 'Cooked' binary format.

Each schema describes how to parse the per-instance bytes of a specific class
in BINARY (.ob save-file) mode. Cooked text mode (.gen files with named
fields) is a different code path and is NOT yet handled here.

Schema format: a list of (name, type, min_version) tuples, evaluated in order.
The current schema_version is taken from the file's class registry entry.

Reverse-engineered from each class's `Serialize()` virtual method (vtable[3]).
Field offsets in comments refer to the C++ struct layout, not the file position.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# Field type codes:
#   "i32"        signed 32-bit
#   "u32"        unsigned 32-bit
#   "u16"        unsigned 16-bit (read as u32 in stream, low half stored)
#   "u8"         unsigned 8-bit
#   "f32"        IEEE 754 float (single precision)
#   "guid16"     16 raw bytes (object instance id)
#   "string"     length-prefixed UTF-8 (u32 length, then bytes)
#   "skip:N"     N raw bytes consumed unparsed (legacy migration shims)
#   "subobj:CLASS"  embedded sub-object with its own class schema
#   "ref"        smart-pointer reference (opaque u64 handle for now)
#   "opaque"     unparsed remainder (terminator)


# ---------------------------------------------------------------------------
# oCDtPlayerProfileData (class id 0x18fd68c1, current schema_version = 8)
# ---------------------------------------------------------------------------
# Decompiled from FUN_1401da580 (vtable[3] of vtable @ 0x140eaf598).
# C++ struct size: 0x20 bytes. Vtable at +0x00 not serialized.
#
# Fields (C++ offsets in comments):
#   +0x08  i32   "field_at_08"    always — has migration logic in old versions
#   +0x0C  i32   "field_at_0c"    schema_version >= 2
#   +0x10  i32   "field_at_10"    schema_version >= 6
#   +0x14  u8    "field_at_14"    schema_version >= 7
#   +0x18  u32   "field_at_18"    schema_version >= 8
#
# Field semantics: not yet identified by name. Likely candidates: chapter index,
# difficulty, hero choice, run state — but all unverified. Empirical mapping
# work needed (compare known-good saves with diff'd state).
SCHEMA_oCDtPlayerProfileData = [
    ("field_at_08", "i32", 0),
    ("field_at_0c", "i32", 2),
    ("field_at_10", "i32", 6),
    ("field_at_14", "u8", 7),
    ("field_at_18", "u32", 8),
]


# ---------------------------------------------------------------------------
# oCDtCurrentRunProfileData (class id 0x18fd68c3, current schema_version = 18)
# ---------------------------------------------------------------------------
# Decompiled from FUN_1401da9a0 (vtable[3] of vtable @ 0x140ed8528).
# C++ struct size: 0x220 bytes. Embeds two oCEntityPersistentDataContainer
# sub-objects at +0x08 and +0x28.
#
# Fields (in serialization order; C++ offsets in comments):
#   +0x08  subobj:oCEntityPersistentDataContainer   schema_version >= 0
#   +0x28  subobj:oCEntityPersistentDataContainer   schema_version >= 1
#   +0x60  custom (FUN_1401c5e30)                   schema_version >= 2
#          legacy version==2: read+discard a string and a u32
#   +0x94  i32                                      schema_version >= 2
#   +0x48  ref (smart pointer)                      schema_version >= 3
#   +0x9c  u8 or f32                                schema_version >= 4
#          legacy versions <8: read named u8
#          legacy versions <16: read 6 extra u32s (migration shims)
#   +0x210 string                                   schema_version >= 4
#   +0xac  u16                                      schema_version >= 5
#   +0xb0  array (FUN_14020b310)                    schema_version >= 7
#   +0xae  u16                                      schema_version >= 7
#          legacy versions 8..12: read+discard a u32
#   +0x50  array (FUN_14020af30)                    schema_version >= 10
#          legacy versions 10..15: read+discard a u32
#   +0x90  u16                                      schema_version >= 11
#   +0x98  custom (FUN_140205710)                   schema_version >= 14
#   +0xc0  custom (FUN_14020ab90)                   schema_version >= 15
#   +0xd0  subobj                                   schema_version >= 17
#   +0xa8  u8 or f32                                schema_version >= 18
#
# This schema is structurally complete but the helper-fn calls
# (FUN_1401c5e30, FUN_14020b310, etc.) parse complex sub-types we haven't
# decoded yet — they're treated as opaque ranges in the parser until
# individually reversed.
SCHEMA_oCDtCurrentRunProfileData_NOTES = """
Schema is documented in comments only; structural complexity (5+ helper-fn
sub-serializers) makes a flat field list misleading. Use save-fields.yaml
or per-field offset edits for now until each helper is reversed.
"""


# ---------------------------------------------------------------------------
# Registry — class name → schema
# ---------------------------------------------------------------------------
SCHEMAS_BY_NAME = {
    "oCDtPlayerProfileData": SCHEMA_oCDtPlayerProfileData,
    # oCDtCurrentRunProfileData intentionally omitted from machine schema —
    # see SCHEMA_oCDtCurrentRunProfileData_NOTES above.
}


# ---------------------------------------------------------------------------
# minimal field reader for the simple schemas


def read_field(reader, type_code: str):
    """Read a single field from a binary stream reader. Returns the value
    (None for skip types). The reader must expose: u8(), u16(), u32(), i32(),
    take(n), and a position counter."""
    if type_code == "i32":
        import struct as _struct
        return _struct.unpack("<i", reader.take(4))[0]
    if type_code == "u32":
        return reader.u32()
    if type_code == "u16":
        # binary mode: read as u32, take low 16 bits
        return reader.u32() & 0xFFFF
    if type_code == "u8":
        return reader.u8()
    if type_code == "f32":
        import struct as _struct
        return _struct.unpack("<f", reader.take(4))[0]
    if type_code == "guid16":
        return reader.take(16).hex()
    if type_code == "string":
        n = reader.u32()
        return reader.take(n).decode("utf-8", errors="replace")
    if type_code.startswith("skip:"):
        n = int(type_code.split(":", 1)[1])
        reader.take(n)
        return None
    raise ValueError(f"unsupported field type: {type_code}")


def parse_schema(reader, schema, schema_version: int) -> dict:
    """Parse a flat-field schema. Returns {field_name: value} dict, including
    only fields whose min_version <= schema_version."""
    out = {}
    for name, type_code, min_v in schema:
        if schema_version >= min_v:
            out[name] = read_field(reader, type_code)
    return out
