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
# oCDtHeroDefinition (class id 0x1768d0c9, current schema_version = 26)
# ---------------------------------------------------------------------------
# Decompiled from FUN_1403150c0 (vtable[3] of vtable @ 0x140f04110), validated
# against Geppetto's herodef cooked .gen file.
#
# Inheritance chain (from class registry of any herodef .gen):
#   oISerializable (uid 0x001da16c, schema_v=0, no fields)
#     oIResource     (uid 0x000017b6, schema_v=1, no fields visible in stream)
#       oCDtDefinition (uid 0x1768ce8e, schema_v=1, 2 bytes via parent dispatch)
#         oCDtHeroDefinition (uid 0x1768d0c9, schema_v=26)
#
# The Serialize at FUN_1403150c0 first calls FUN_1403076b0 = oCDtDefinition's
# Serialize (which reads 2 bytes when its schema_v >= 1), then walks its own
# version-gated fields. The fields below capture stream order for the
# schema_v 26 path; legacy migration paths for older schema_v values are NOT
# represented here (would require extending the parser to support gated-skip).
#
# Field-type tags used here (in addition to the primitives above):
#   "two_string"        -- FUN_1401c5e30 — two length-prefixed UTF-8 strings.
#                         Stream cost: 4 + len1 + 4 + len2.
#   "composite"         -- FUN_140670af0 — u32 ver + two_string + u32 type +
#                         conditional (4-byte length + len bytes) string.
#   "vec_obj_ref"       -- FUN_140209ce0 — optional class-info preamble + u32
#                         count + count×u32 ReadObjectRef indices + (if had
#                         preamble) trailing u32.
#   "vec_two_string"    -- FUN_14030d450 — same preamble pattern, elements are
#                         two_string structs.
#   "u8_array_fixed5"   -- FUN_1403343d0 — u32 count + min(count, 5) bytes;
#                         if count > 5, count − 5 extra discard bytes follow.
#   "two_string_array_fixed5" -- FUN_140333ca0 — u32 count + min(count, 5)
#                         two_string elements; if count > 5, count − 5 extras.
#   "subobj_array_fixed7" -- FUN_1403340e0 — u32 count + min(count, 7) named
#                         sub-objects (vtable+0xa0 each).
#   "named_subobject"   -- vtable+0xa0 (FUN_1404e7ff0) — 0xAABB1111 marker +
#                         u32 uClassInfoIndex + recursive object body +
#                         0xAABB2222 marker.
#
# Inheritance-prefix fields:
SCHEMA_oCDtHeroDefinition_PARENT = [
    # oCDtDefinition::Serialize (FUN_1403076b0). Reads when its schema_v >= 1.
    # Note: gating by parent's schema_version is NOT yet wired in the parser;
    # this entry assumes oCDtDefinition v1 is present (universally true in the
    # current build's .gen files).
    ("parent_oCDtDefinition_b285", "u8", 0),
    ("parent_oCDtDefinition_b284", "u8", 0),
]

# oCDtHeroDefinition's own fields, in stream order, with min_version gates
# (schema_version values are file-specific; current build = 26):
SCHEMA_oCDtHeroDefinition_OWN = [
    ("u32_at_2b0",                 "u32", 0),
    ("twoStr_at_2b8",              "two_string", 0),
    ("composite_at_328",           "composite", 0),

    ("twoStr_at_5d8",              "two_string", 1),
    ("twoStr_at_610",              "two_string", 1),
    ("twoStr_at_648",              "two_string", 1),
    ("twoStr_at_680",              "two_string", 1),

    ("vec_obj_ref_at_8a0",         "vec_obj_ref", 3),
    ("vec_two_string_at_7d0",      "vec_two_string", 4),
    ("twoStr_at_2f0",              "two_string", 6),
    ("u8_array_fixed5_at_7e0",     "u8_array_fixed5", 8),
    ("vec_obj_ref_at_8b0",         "vec_obj_ref", 10),
    ("two_string_array_fixed5_at_6b8", "two_string_array_fixed5", 11),

    ("guid16_at_290",              "guid16", 12),
    ("u8_at_2a0",                  "u8", 12),
    ("u32_at_2a4",                 "u32", 12),

    ("vec_obj_ref_at_8c0",         "vec_obj_ref", 13),
    ("composite_at_398",           "composite", 14),
    ("named_subobject_at_828",     "named_subobject", 15),
    ("composite_at_408",           "composite", 16),
    ("string_at_4e8",              "string", 17),
    ("u8_at_4f8",                  "u8", 18),
    ("twoStr_at_7e8",              "two_string", 19),
    # legacy migration paths (v in [20..25]) consume bytes into discarded
    # locals; not modeled here. The current-build path goes through:
    ("u8_at_821",                  "u8", 21),
    ("u8_at_820",                  "u8", 23),
    ("composite_at_478",           "composite", 23),
    ("u8_at_822",                  "u8", 24),
    ("u8_at_823",                  "u8", 25),
    ("named_subobject_at_500",     "named_subobject", 26),
]

SCHEMA_oCDtHeroDefinition = SCHEMA_oCDtHeroDefinition_PARENT + SCHEMA_oCDtHeroDefinition_OWN


# ---------------------------------------------------------------------------
# oCEntitySettings (class id 0x0c3b9daa, current schema_version = 8)
# ---------------------------------------------------------------------------
# Decompiled from FUN_1406c7760 (vtable[3] of vtable @ 0x140f4cee8).
# Parent: oCSpawnableSettings (schema_v=0, no fields). No explicit parent
# dispatch in the Serialize.
SCHEMA_oCEntitySettings = [
    ("vec_obj_ref_at_118",      "vec_obj_ref",       0),  # vec<u32 obj-ref>
    ("u8_at_78",                "u8",                1),
    ("u8_array_fixed16_at_1b8", "u8_array_fixed16",  4),  # FUN_1405cfe40
    ("vec_two_string_at_e8",    "vec_two_string",    5),  # FUN_140208d00
    ("u32_obj_ref_at_1c8",      "u32",               7),  # vtable+0xa8 = u32 obj-ref
    ("vec_obj_ref_at_f8",       "vec_obj_ref",       8),  # FUN_1402b95b0
]


# ---------------------------------------------------------------------------
# oIEntityCpntSettings (class id 0x0c608329, current schema_version = 20)
# ---------------------------------------------------------------------------
# Decompiled from FUN_1406f4b90 (parent dispatch in
# oCEntityCpntEntitySpawnerSettings::Serialize). The current-build schema_v
# is 20; the legacy v < 20 paths involve numerous version-specific reads
# that this schema does NOT model. For v >= 20, the field stream is below.
#
# Note: a few entries consume bytes into local buffers that are unused at
# v >= 20 (legacy migration shims). They are tagged with "discard_local_*"
# in the field name; their value is read but irrelevant to the entity.
SCHEMA_oIEntityCpntSettings = [
    ("named_subobject_at_a8",   "named_subobject",  12),
    ("guid16_at_98",            "guid16",           11),
    ("string_at_e8",            "string",           11),
    ("u8_at_33",                "u8",                0),
    ("u8_at_34",                "u8",                0),
    ("u8_at_35",                "u8",                5),
    ("u8_at_36",                "u8",                2),
    ("string_at_38",            "string",            1),
    ("u8_at_81",                "u8",                7),
    ("u8_discard_local_8c",     "u8",                8),  # consumed; unused at v>=0x14
    ("u32_max3_at_84",          "u32",              10),
    ("u8_at_32",                "u8",               19),
]


# ---------------------------------------------------------------------------
# oCEntityCpntEntitySpawnerSettings (class id 0x0ff3b3ab, current schema_v=21)
# ---------------------------------------------------------------------------
# Decompiled from FUN_1407116c0 (vtable[3] of vtable @ 0x140f515a0).
# Parent: oIEntityCpntSettings (handled via FUN_1406f4b90 = parent Serialize
# dispatch at the top of the function). The schema below pre-resolves the
# parent's v=20 field set, then adds the spawner's own v=21 fields.
#
# KEY FIELDS for the parallel agent's spawn-from-anywhere hunt:
#   +0x1bc  u32 (engine validates `<= 2`)  -- TETHER MODE candidate
#                                              0/1/2 = untethered/tethered/?
#   +0x1c0  named_subobject               -- paired settings ref (likely
#                                              owner/pool override)
#   +0x138  named_subobject (first prominent)
#                                          -- "what to spawn" template ref
_OIENTITYCPNTSETTINGS_V20_INHERITED = [
    ("oIEntityCpnt.named_subobject_at_a8", "named_subobject", 0),
    ("oIEntityCpnt.guid16_at_98",          "guid16",           0),
    ("oIEntityCpnt.string_at_e8",          "string",           0),
    ("oIEntityCpnt.u8_at_33",              "u8",               0),
    ("oIEntityCpnt.u8_at_34",              "u8",               0),
    ("oIEntityCpnt.u8_at_35",              "u8",               0),
    ("oIEntityCpnt.u8_at_36",              "u8",               0),
    ("oIEntityCpnt.string_at_38",          "string",           0),
    ("oIEntityCpnt.u8_at_81",              "u8",               0),
    ("oIEntityCpnt.u8_discard_local_8c",   "u8",               0),
    ("oIEntityCpnt.u32_max3_at_84",        "u32",              0),
    ("oIEntityCpnt.u8_at_32",              "u8",               0),
]

SCHEMA_oCEntityCpntEntitySpawnerSettings = _OIENTITYCPNTSETTINGS_V20_INHERITED + [
    ("named_subobject_at_138",     "named_subobject", 16),  # "what to spawn"
    ("named_subobject_at_7b0",     "named_subobject",  5),
    ("u32_tether_mode_at_1bc",     "u32",              9),  # TETHER mode (max 2)
    ("named_subobject_at_1c0",     "named_subobject",  9),  # paired override
    ("named_subobject_at_200",     "named_subobject", 19),
    ("named_subobject_at_10e0",    "named_subobject",  8),
    ("named_subobject_at_1060",    "named_subobject",  8),
    ("named_subobject_at_1990",    "named_subobject", 17),
    ("named_subobject_at_19d0",    "named_subobject", 17),
    ("named_subobject_at_f8",      "named_subobject", 13),
    ("vec_picker_at_1a78",         "vec_picker",      14),
    ("u8_at_19f0",                 "u8",              18),
    ("named_subobject_at_19f8",    "named_subobject", 18),
    ("u8_at_1b8",                  "u8",              21),
]


# ---------------------------------------------------------------------------
# Registry — class name → schema
# ---------------------------------------------------------------------------
SCHEMAS_BY_NAME = {
    "oCDtPlayerProfileData": SCHEMA_oCDtPlayerProfileData,
    "oCDtHeroDefinition": SCHEMA_oCDtHeroDefinition,
    "oCEntitySettings": SCHEMA_oCEntitySettings,
    "oIEntityCpntSettings": SCHEMA_oIEntityCpntSettings,
    "oCEntityCpntEntitySpawnerSettings": SCHEMA_oCEntityCpntEntitySpawnerSettings,
    # oCDtCurrentRunProfileData intentionally omitted from machine schema —
    # see SCHEMA_oCDtCurrentRunProfileData_NOTES above.
}


# ---------------------------------------------------------------------------
# Helper readers (engine-side helper functions resolved by RE)
# ---------------------------------------------------------------------------

import struct as _struct


def _read_two_string(reader) -> dict:
    """FUN_1401c5e30. Two length-prefixed strings; in-memory flag derived,
    not on-wire."""
    n1 = reader.u32()
    s1 = reader.take(n1).decode("utf-8", errors="replace") if n1 else ""
    n2 = reader.u32()
    s2 = reader.take(n2).decode("utf-8", errors="replace") if n2 else ""
    return {"s1": s1, "s2": s2}


def _read_composite(reader) -> dict:
    """FUN_140670af0. ver-u32 + two_string + type-u32 + (if ver != 0) string."""
    ver = reader.u32()
    ts = _read_two_string(reader)
    type_id = reader.u32()
    extra = None
    if ver != 0:
        n = reader.u32()
        extra = reader.take(n).decode("utf-8", errors="replace") if n else ""
    return {"ver": ver, "two_string": ts, "type": type_id, "extra": extra}


def _maybe_read_class_preamble(reader) -> tuple[bool, int]:
    """Vector helpers (FUN_140209ce0, FUN_14030d450) optionally emit a
    class-info preamble before the count. Returns (had_preamble, count).

    Wire format (when present):
      u32 0xAABB1111
      string class_name1
      u32, u32        (class metadata fields)
      if class_name1 != "oISerializable":
          string class_name2
          u32, u32
      u32 actual_count
    """
    saved = reader.pos
    first = reader.u32()
    if first != 0xAABB1111:
        return (False, first)
    n1 = reader.u32()
    cn1 = reader.take(n1).decode("utf-8", errors="replace") if n1 else ""
    reader.u32()
    reader.u32()
    if cn1 != "oISerializable":
        n2 = reader.u32()
        reader.take(n2)
        reader.u32()
        reader.u32()
    count = reader.u32()
    return (True, count)


def _read_vec_obj_ref(reader) -> dict:
    """FUN_140209ce0. Optional class-info preamble + count + N×u32 obj-ref."""
    had_pre, count = _maybe_read_class_preamble(reader)
    if count > 1_000_000:
        raise ValueError(f"vec_obj_ref count implausible: {count}")
    refs = [reader.u32() for _ in range(count)]
    if had_pre:
        reader.u32()  # trailing u32 emitted alongside preamble
    return {"count": count, "refs": refs, "had_preamble": had_pre}


def _read_vec_two_string(reader) -> dict:
    """FUN_14030d450. Same preamble pattern as vec_obj_ref; elements are
    two_string structs."""
    had_pre, count = _maybe_read_class_preamble(reader)
    if count > 1_000_000:
        raise ValueError(f"vec_two_string count implausible: {count}")
    items = [_read_two_string(reader) for _ in range(count)]
    if had_pre:
        reader.u32()
    return {"count": count, "items": items, "had_preamble": had_pre}


def _read_u8_array_fixed5(reader) -> dict:
    """FUN_1403343d0. u32 count + min(count, 5) bytes; if count > 5, count − 5
    extra bytes (also consumed)."""
    count = reader.u32()
    n_bytes = count if count <= 5 else count
    raw = reader.take(n_bytes)
    return {"count": count, "bytes": raw.hex()}


def _read_two_string_array_fixed5(reader) -> dict:
    """FUN_140333ca0. u32 count + min(count, 5) two_strings; if count > 5,
    extras included."""
    count = reader.u32()
    items = [_read_two_string(reader) for _ in range(count)]
    return {"count": count, "items": items}


def _read_named_subobject(reader) -> dict:
    """vtable+0xa0 (FUN_1404e7ff0). 0xAABB1111 + u32 uClassInfoIndex + body +
    0xAABB2222. Body is opaque here — it would dispatch to its own class's
    Serialize. We scan to the matching 0xAABB2222 (handling nested pairs)."""
    mark = reader.u32()
    if mark != 0xAABB1111:
        raise ValueError(f"expected 0xAABB1111 sub-object marker, got 0x{mark:08x}")
    class_info_idx = reader.u32()
    body_start = reader.pos
    depth = 1
    data = reader.data
    pos = reader.pos
    while pos + 4 <= len(data):
        (w,) = _struct.unpack_from("<I", data, pos)
        if w == 0xAABB1111:
            depth += 1
            pos += 4
        elif w == 0xAABB2222:
            depth -= 1
            pos += 4
            if depth == 0:
                break
        else:
            pos += 1
    if depth != 0:
        raise ValueError("named_subobject: unbalanced markers")
    body = data[body_start : pos - 4]
    reader.pos = pos
    body_preview = body[:24].hex()
    if len(body) > 24:
        body_preview += "..."
    return {
        "class_info_idx": class_info_idx,
        "body_size": len(body),
        "body_preview": body_preview,
    }


def _read_u8_array_fixed16(reader) -> dict:
    """FUN_1405cfe40. u32 count + min(count, 16) bytes; if count > 16, count − 16
    extra bytes (also consumed)."""
    count = reader.u32()
    raw = reader.take(count)
    return {"count": count, "bytes": raw.hex()}


def _read_vec_picker(reader) -> dict:
    """FUN_1402f14d0. Vector of `oCEntityCpntPicker` instances; same optional
    class-info preamble as other vectors. Each element is read via
    vtable+0xa0 (named_subobject)."""
    had_pre, count = _maybe_read_class_preamble(reader)
    if count > 1_000_000:
        raise ValueError(f"vec_picker count implausible: {count}")
    items = [_read_named_subobject(reader) for _ in range(count)]
    if had_pre:
        reader.u32()
    return {"count": count, "items_count": len(items), "had_preamble": had_pre}


_HELPER_READERS = {
    "two_string": _read_two_string,
    "composite": _read_composite,
    "vec_obj_ref": _read_vec_obj_ref,
    "vec_two_string": _read_vec_two_string,
    "u8_array_fixed5": _read_u8_array_fixed5,
    "u8_array_fixed16": _read_u8_array_fixed16,
    "two_string_array_fixed5": _read_two_string_array_fixed5,
    "named_subobject": _read_named_subobject,
    "vec_picker": _read_vec_picker,
}


# ---------------------------------------------------------------------------
# Field reader & schema parser
# ---------------------------------------------------------------------------


def read_field(reader, type_code: str):
    """Read a single field from a binary stream reader. Returns the value
    (None for skip types). The reader must expose: u8(), u16(), u32(), i32(),
    take(n), and a position counter."""
    if type_code in _HELPER_READERS:
        return _HELPER_READERS[type_code](reader)
    if type_code == "i32":
        return _struct.unpack("<i", reader.take(4))[0]
    if type_code == "u32":
        return reader.u32()
    if type_code == "u16":
        return reader.u32() & 0xFFFF
    if type_code == "u8":
        return reader.u8()
    if type_code == "f32":
        return _struct.unpack("<f", reader.take(4))[0]
    if type_code == "guid16":
        return reader.take(16).hex()
    if type_code == "string":
        n = reader.u32()
        return reader.take(n).decode("utf-8", errors="replace") if n else ""
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
