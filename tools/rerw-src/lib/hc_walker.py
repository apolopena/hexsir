"""Walk the HeroController persistent-data body to resolve field offsets dynamically.

The wire format includes variable-length sections (HeroIngredient vector,
HeroMOPersistentData vector, several `vec_guid16` sequences) whose sizes
shift with content. Hardcoded offsets calibrated against one chapter's
shape don't survive into other chapters; the walker reads counts and snaps
past framed sub-objects (using the cooked tree's child list) to compute
the actual byte position of each named field at runtime.

Returns a `dict[str, (offset, length)]` keyed by field name. Useful keys
for mint operations: `held_dream_shards`, `dream_shards_earned`,
`dream_shards_spent`, `raven_feathers_consumed`, `stars_of_fate`,
`ingredient_vec_count`, `hmo_vec_count`.
"""

from __future__ import annotations

import struct

from lib import cooked


def walk_hc_body(
    body: bytes,
    hc_children: list[cooked.TreeNode],
    hc_start: int,
    hc_class_schema: int,
) -> dict[str, tuple[int, int]]:
    """Walk HC body using the cooked tree's children to snap past framed records.

    Args:
        body: HC body bytes (between class_index and end marker).
        hc_children: HC TreeNode's children list.
        hc_start: HC frame start offset within object_section (used to
            compute child body-relative positions).
        hc_class_schema: HC class registry's schema_version.

    Returns:
        Mapping of named fields to (body_offset, length).
    """
    fmap: dict[str, tuple[int, int]] = {}
    pos = 0

    cstarts = [(c.start - hc_start - 8) for c in hc_children]
    cends = [(c.end - hc_start - 8) for c in hc_children]

    def record(name: str, length: int) -> None:
        nonlocal pos
        fmap[name] = (pos, length)
        pos += length

    record("guid", 16)
    record("flag_byte", 1)
    record("damage_float_1", 4)
    record("damage_float_2", 4)
    # +0x19: total Dream Shards earned this run (held + dream_shards_spent).
    record("dream_shards_earned", 4)
    # +0x1d: held Dream Shards — HUD-displayed spendable count.
    # Authoritative direct-read field; HUD does NOT recompute earned − spent.
    record("held_dream_shards", 4)

    (ing_count,) = struct.unpack_from("<I", body, pos)
    record("ingredient_vec_count", 4)
    ing_consumed = 0
    while ing_consumed < ing_count:
        matched = next((i for i, cs in enumerate(cstarts) if cs == pos), None)
        if matched is None:
            raise RuntimeError(
                f"expected ingredient frame at HC body+0x{pos:x}, none in children"
            )
        record(
            f"ingredient_record_{ing_consumed}",
            cends[matched] - cstarts[matched],
        )
        ing_consumed += 1

    record("raven_feathers_consumed", 4)
    if hc_class_schema >= 1:
        record("stars_of_fate", 4)
    if hc_class_schema >= 2:
        record("field_at_0x90", 4)
    if hc_class_schema >= 3:
        for i in range(10):
            record(f"talent_count_{i}", 4)

    first_hmo_idx = None
    for i, cs in enumerate(cstarts):
        if cs >= pos and i >= ing_count:
            first_hmo_idx = i
            break
    if first_hmo_idx is None:
        raise RuntimeError("no HMO frame found in HC children")
    first_hmo_start = cstarts[first_hmo_idx]

    pre_hmo_unframed_bytes = first_hmo_start - 4 - pos
    if pre_hmo_unframed_bytes < 0:
        raise RuntimeError(
            f"pre-HMO unframed region negative: pos=+0x{pos:x} "
            f"first_hmo=+0x{first_hmo_start:x}"
        )
    record("pre_hmo_unframed_blob", pre_hmo_unframed_bytes)

    (hmo_count,) = struct.unpack_from("<I", body, pos)
    record("hmo_vec_count", 4)
    hmo_consumed = 0
    while hmo_consumed < hmo_count:
        matched = next((i for i, cs in enumerate(cstarts) if cs == pos), None)
        if matched is None:
            raise RuntimeError(
                f"expected HMO frame at HC body+0x{pos:x}, none in children"
            )
        record(f"hmo_record_{hmo_consumed}", cends[matched] - cstarts[matched])
        hmo_consumed += 1

    def read_u32_vec(name_count: str, name_payload: str, item_size: int) -> int:
        (n,) = struct.unpack_from("<I", body, pos)
        record(name_count, 4)
        record(name_payload, n * item_size)
        return n

    read_u32_vec("vec_guid16_b_count", "vec_guid16_b_payload", 16)
    read_u32_vec("vec_guid16_c_count", "vec_guid16_c_payload", 16)
    read_u32_vec("vec_guid16_d_count", "vec_guid16_d_payload", 16)
    record("FUN_1403b4140_blob", 4)
    record("dream_shards_spent", 4)
    read_u32_vec("vec_32byte_count", "vec_32byte_payload", 32)

    (str_count,) = struct.unpack_from("<I", body, pos)
    record("vec_string_count", 4)
    for i in range(str_count):
        (slen,) = struct.unpack_from("<I", body, pos)
        record(f"vec_string_{i}_len", 4)
        record(f"vec_string_{i}_payload", slen)

    return fmap
