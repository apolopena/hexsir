"""Pure setter functions for save fields.

Each setter takes a parsed `cooked.CookedFile` and a value, and mutates
`cf.object_section` in place. The caller is responsible for re-encoding
the file (which auto-recomputes the body CRC32).

Two layers of CLI consume these:
  - `rerw mint savefile` calls every relevant zero/clean-default setter
    in sequence to produce a clean starting save.
  - `rerw write savefile <field> <value>` calls one setter per invocation
    for granular edits to an existing save.

Setters validate inputs and raise `ValueError` for out-of-range values
or `FieldNotFound` when a target class instance is missing from the save.
"""

from __future__ import annotations

import struct

from lib import cooked
from lib.hc_walker import walk_hc_body

HC_CLASS = "oCDtEntityCpntHeroControllerPersistentData"
GL_CLASS = "oCDtEntityCpntGroupLevelPersistentData"
HSD_CLASS = "HeroScoreData"
CRP_CLASS = "oCDtCurrentRunProfileData"


class FieldNotFound(Exception):
    """Raised when a setter can't locate its target field's class instance."""


def _find_unique(cf: cooked.CookedFile, roots, class_name: str) -> cooked.TreeNode:
    hits = list(cooked.find_class_in_tree(cf, roots, class_name))
    if len(hits) != 1:
        raise FieldNotFound(
            f"expected exactly 1 instance of {class_name}, found {len(hits)}"
        )
    return hits[0][1]


def _post_vec_offset(hc_body: bytes) -> int:
    """First post-ingredient-vector u32 offset (Raven Feathers consumed).
    Stars of Fate sits at +0x04 from this.
    """
    vec_count = struct.unpack_from("<I", hc_body, 0x21)[0]
    return 0x25 + 20 * vec_count


# --- Single-value setters ---


def set_stars(cf: cooked.CookedFile, count: int) -> int:
    """Set Stars of Fate live spendable count. Returns the old value."""
    if count < 0:
        raise ValueError(f"stars must be >= 0, got {count}")
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    hc = _find_unique(cf, roots, HC_CLASS)
    hcb = hc.start + 8
    hc_body = bytes(section[hcb : hc.end - 4])
    pv = _post_vec_offset(hc_body)
    old = struct.unpack_from("<I", section, hcb + pv + 0x04)[0]
    struct.pack_into("<I", section, hcb + pv + 0x04, count)
    cf.object_section = bytes(section)
    return old


def set_held_feathers(cf: cooked.CookedFile, count: int) -> int:
    """Set held Raven Feathers count. Returns the old value."""
    if count < 0:
        raise ValueError(f"feathers must be >= 0, got {count}")
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    crp = _find_unique(cf, roots, CRP_CLASS)
    off = crp.start + 8 + 0x15D
    old = struct.unpack_from("<I", section, off)[0]
    struct.pack_into("<I", section, off, count)
    cf.object_section = bytes(section)
    return old


def set_hero_level(cf: cooked.CookedFile, level: int) -> int:
    """Set in-run hero level. Returns the old value."""
    if level < 1:
        raise ValueError(f"level must be >= 1, got {level}")
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    gl = _find_unique(cf, roots, GL_CLASS)
    off = gl.start + 8 + 0x11
    old = struct.unpack_from("<I", section, off)[0]
    struct.pack_into("<I", section, off, level)
    cf.object_section = bytes(section)
    return old


def set_hero_xp(cf: cooked.CookedFile, xp: int) -> int:
    """Set accumulated XP. Returns the old value."""
    if xp < 0:
        raise ValueError(f"xp must be >= 0, got {xp}")
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    gl = _find_unique(cf, roots, GL_CLASS)
    off = gl.start + 8 + 0x15
    old = struct.unpack_from("<I", section, off)[0]
    struct.pack_into("<I", section, off, xp)
    cf.object_section = bytes(section)
    return old


def set_feathers_spent(cf: cooked.CookedFile, count: int) -> int:
    """Set the per-run "Raven Feathers consumed" score-page stat.
    Independent of held feathers. Returns the old value.
    """
    if count < 0:
        raise ValueError(f"feathers spent must be >= 0, got {count}")
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    hc = _find_unique(cf, roots, HC_CLASS)
    hcb = hc.start + 8
    hc_body = bytes(section[hcb : hc.end - 4])
    pv = _post_vec_offset(hc_body)
    old = struct.unpack_from("<I", section, hcb + pv)[0]
    struct.pack_into("<I", section, hcb + pv, count)
    cf.object_section = bytes(section)
    return old


# --- Per-run state zeroers (used by mint) ---


def zero_per_run_damage(cf: cooked.CookedFile) -> tuple[float, float, float, float]:
    """Zero the 4 damage floats at HC body+0x11..+0x21. Returns the old
    values as a 4-tuple."""
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    hc = _find_unique(cf, roots, HC_CLASS)
    hcb = hc.start + 8
    olds = struct.unpack_from("<ffff", section, hcb + 0x11)
    section[hcb + 0x11 : hcb + 0x21] = b"\x00" * 16
    cf.object_section = bytes(section)
    return olds


def zero_dream_shards_spent(cf: cooked.CookedFile) -> float:
    """Zero the per-run "Dream Shards spent" stat. Offset is dynamic and
    resolved via the HC walker — varies across chapters. Returns the old
    value."""
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    hc = _find_unique(cf, roots, HC_CLASS)
    hcb = hc.start + 8
    hc_body = bytes(section[hcb : hc.end - 4])
    hc_class = next(c for c in cf.classes if c.name == HC_CLASS)
    fmap = walk_hc_body(hc_body, hc.children, hc.start, hc_class.schema_version)
    ds_off, _ = fmap["dream_shards_spent"]
    old = struct.unpack_from("<f", section, hcb + ds_off)[0]
    struct.pack_into("<f", section, hcb + ds_off, 0.0)
    cf.object_section = bytes(section)
    return old


def zero_score_floats(cf: cooked.CookedFile) -> int:
    """Zero the 28 HeroScoreData score floats. Counts and trailing
    nickname string are preserved. Returns the count of floats zeroed (28)."""
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    hsd = _find_unique(cf, roots, HSD_CLASS)
    hsdb = hsd.start + 8
    section[hsdb + 0x04 : hsdb + 0x18] = b"\x00" * 20
    section[hsdb + 0x1C : hsdb + 0x44] = b"\x00" * 40
    section[hsdb + 0x48 : hsdb + 0x58] = b"\x00" * 16
    section[hsdb + 0x5C : hsdb + 0x68] = b"\x00" * 12
    section[hsdb + 0x6C : hsdb + 0x84] = b"\x00" * 24
    cf.object_section = bytes(section)
    return 28


def zero_playtime(cf: cooked.CookedFile) -> float:
    """Zero the CRP playtime float (CRP body+0xE5). Returns the old value."""
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    crp = _find_unique(cf, roots, CRP_CLASS)
    off = crp.start + 8 + 0xE5
    old = struct.unpack_from("<f", section, off)[0]
    struct.pack_into("<f", section, off, 0.0)
    cf.object_section = bytes(section)
    return old


def zero_chapter_banner(cf: cooked.CookedFile) -> int:
    """Zero the end-screen chapter-progression banner u32 in CRP body
    (the u32 immediately preceding the ActivityScore vector count).
    Returns the old value, or 0 if no AS records (banner u32 not present).
    """
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    crp = _find_unique(cf, roots, CRP_CLASS)
    as_indices = [
        i
        for i, ch in enumerate(crp.children)
        if cf.classes[ch.class_index].name == "ActivityScore"
    ]
    if not as_indices:
        return 0
    first_as = crp.children[as_indices[0]]
    off = first_as.start - 8
    old = struct.unpack_from("<I", section, off)[0]
    struct.pack_into("<I", section, off, 0)
    cf.object_section = bytes(section)
    return old


def remove_activity_scores(cf: cooked.CookedFile) -> int:
    """Remove all ActivityScore records from CRP body and zero the parent
    count u32. Returns the number of records removed.

    Must run AFTER any other CRP-body edit (HSD, playtime, etc.) because
    snipping AS frames shifts byte offsets of anything after them.
    """
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    crp = _find_unique(cf, roots, CRP_CLASS)
    as_indices = [
        i
        for i, ch in enumerate(crp.children)
        if cf.classes[ch.class_index].name == "ActivityScore"
    ]
    if not as_indices:
        cf.object_section = bytes(section)
        return 0
    expected = list(range(as_indices[0], as_indices[-1] + 1))
    if as_indices != expected:
        raise FieldNotFound(
            f"ActivityScore children not contiguous in CRP: indices={as_indices}"
        )
    first_as = crp.children[as_indices[0]]
    last_as = crp.children[as_indices[-1]]
    count_off = first_as.start - 4
    current_count = struct.unpack_from("<I", section, count_off)[0]
    if current_count != len(as_indices):
        raise FieldNotFound(
            f"ActivityScore parent count mismatch: u32@0x{count_off:x}="
            f"{current_count}, child count={len(as_indices)}"
        )
    struct.pack_into("<I", section, count_off, 0)
    del section[first_as.start : last_as.end]
    cf.object_section = bytes(section)
    return len(as_indices)
