"""Mint a starting save by stripping per-run state from a chapter-boss-kill proof.

The mint recipe takes a chapter-boss-kill proof save and produces a clean
chapter-N starting save by zeroing per-run accumulated state (damage stats,
dream shards, score data, playtime), resetting hero level and XP, optionally
setting the Stars of Fate baseline, rolling the chapter index, and removing
the per-run ActivityScore records (which would otherwise carry chapter-N
icons forward into the score-details panel).

Two design notes worth knowing:

1. ActivityScore records are REMOVED (not preserved). Earlier versions of
   the recipe truncated each AS body to a 25-byte zero stub, which trips
   the loader's per-class deserialize and registers the save silencer
   (Error code 4 -> SaveCompat modal -> all subsequent saves silently
   no-op for the rest of the session). The follow-on fix preserved bodies
   verbatim, which avoided the silencer but left chapter-N icons on the
   score-details panel. The current recipe removes the records entirely
   and zeroes the parent's count u32, so the deserialize loop runs zero
   iterations and no icons render. See
   `rw/key-findings/save-silencer-mechanism.md` and the
   `as-count-zero__from-...` chapter-1 golden's breakthrough.md.

2. HeroController body field offsets shift with chapter content (the
   HeroIngredient and HeroMOPersistentData vectors and several unframed
   `vec_guid16` sequences vary in length). The mint resolves
   `dream_shards_spent` dynamically via `lib.hc_walker.walk_hc_body`,
   so the same recipe works across chapters without a body-size gate.

All edits operate on a `bytearray` view of `cooked.CookedFile.object_section`;
the caller re-encodes the file (which auto-recomputes the body CRC32).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from lib import cooked
from lib.hc_walker import walk_hc_body


@dataclass
class MintConfig:
    """Mint parameters. None means 'do not modify this slot'."""

    stars_of_fate: int | None = 7
    hero_level: int | None = 1
    hero_xp: int | None = 0


@dataclass
class MintReport:
    """Per-step record of what the mint actually did."""

    steps: list[str]


class MintError(Exception):
    """Raised when the source save lacks an expected class instance."""


def _body_off(node: cooked.TreeNode) -> int:
    """Start offset of a node's body bytes within object_section."""
    return node.start + 8


def _find_unique(cf: cooked.CookedFile, roots, class_name: str) -> cooked.TreeNode:
    hits = list(cooked.find_class_in_tree(cf, roots, class_name))
    if len(hits) != 1:
        raise MintError(
            f"expected exactly 1 instance of {class_name}, found {len(hits)}"
        )
    return hits[0][1]


def mint_object_section(cf: cooked.CookedFile, config: MintConfig) -> MintReport:
    """Apply mint transformations to `cf.object_section` in place.

    The caller is responsible for re-encoding the file (which recomputes CRC).
    """
    section = bytearray(cf.object_section)
    roots = cooked.parse_object_tree(cf)
    steps: list[str] = []

    # 1. HeroController per-run damage stats and dream-shards collected.
    hc = _find_unique(cf, roots, "oCDtEntityCpntHeroControllerPersistentData")
    hcb = _body_off(hc)
    hc_body_len = hc.end - hc.start - 12
    hc_body = bytes(section[hcb : hcb + hc_body_len])
    hc_class = next(
        c
        for c in cf.classes
        if c.name == "oCDtEntityCpntHeroControllerPersistentData"
    )
    fmap = walk_hc_body(hc_body, hc.children, hc.start, hc_class.schema_version)

    section[hcb + 0x11 : hcb + 0x21] = b"\x00" * 16
    steps.append("HC damage floats (+0x11..+0x21) -> zero")

    ds_off, _ = fmap["dream_shards_spent"]
    struct.pack_into("<f", section, hcb + ds_off, 0.0)
    steps.append(f"HC dream-shards-spent (dynamic +0x{ds_off:x}) -> 0.0")

    # 2. HC HeroIngredient vector at +0x21 -- compute the post-vector field
    # base. Each oSDtHeroIngredient record is a framed sub-object of 20 bytes
    # (4 mark_start + 4 class_idx + 8 body + 4 mark_end). The first u32 after
    # the vector is "Raven Feathers consumed"; the next u32 is Stars of Fate.
    ingredient_vec_count = struct.unpack_from("<I", section, hcb + 0x21)[0]
    post_vec = 0x25 + 20 * ingredient_vec_count
    steps.append(
        f"HC ingredient vec count = {ingredient_vec_count} "
        f"(post-vector fields begin at HC body+0x{post_vec:x})"
    )

    struct.pack_into("<I", section, hcb + post_vec, 0)
    steps.append(f"HC raven-feathers-consumed (+0x{post_vec:x}) -> 0")

    if config.stars_of_fate is not None:
        struct.pack_into(
            "<I", section, hcb + post_vec + 0x04, config.stars_of_fate
        )
        steps.append(
            f"HC stars-of-fate (+0x{post_vec + 0x04:x}) -> {config.stars_of_fate}"
        )

    # 3. HeroScoreData -- zero the 28 score floats in place. Body has 5 groups,
    # each "u32 count + count*float". Preserve counts and trailing string+tail.
    # Must run BEFORE the ActivityScore removal (HSD sits AFTER AS records in
    # CRP body; its absolute offset shifts when AS frames are snipped).
    hsd = _find_unique(cf, roots, "HeroScoreData")
    hsdb = _body_off(hsd)
    section[hsdb + 0x04 : hsdb + 0x18] = b"\x00" * 20  # 5 floats
    section[hsdb + 0x1C : hsdb + 0x44] = b"\x00" * 40  # 10 floats
    section[hsdb + 0x48 : hsdb + 0x58] = b"\x00" * 16  # 4 floats
    section[hsdb + 0x5C : hsdb + 0x68] = b"\x00" * 12  # 3 floats
    section[hsdb + 0x6C : hsdb + 0x84] = b"\x00" * 24  # 6 floats
    steps.append("HeroScoreData: 28 score floats -> zero (counts/string preserved)")

    # 4. CurrentRunProfileData playtime float at +0xe5 (byte-misaligned).
    # +0xE5 is stable across chapters because CRP's preamble is two
    # oCEntityPersistentDataContainer frames with constant body sizes 144/8.
    crp = _find_unique(cf, roots, "oCDtCurrentRunProfileData")
    crpb = _body_off(crp)
    struct.pack_into("<f", section, crpb + 0xE5, 0.0)
    steps.append("CurrentRunProfileData playtime float (+0xe5) -> 0.0")

    # 5. GroupLevel: in-run hero level + accumulated XP.
    if config.hero_level is not None or config.hero_xp is not None:
        gl = _find_unique(cf, roots, "oCDtEntityCpntGroupLevelPersistentData")
        glb = _body_off(gl)
        if config.hero_level is not None:
            struct.pack_into("<I", section, glb + 0x11, config.hero_level)
            steps.append(f"GroupLevel hero_level (+0x11) -> {config.hero_level}")
        if config.hero_xp is not None:
            struct.pack_into("<I", section, glb + 0x15, config.hero_xp)
            steps.append(f"GroupLevel hero_xp (+0x15) -> {config.hero_xp}")

    # 6. ActivityScore removal -- runs LAST because it shrinks CRP body
    # (anything after the AS records has its byte offset shifted up).
    # The deserialize loop reads `count` from the parent (CRP) body and
    # iterates that many times; with count=0 and the frames removed,
    # ActivityScore_Serialize never runs and no chapter-N icons render
    # on the score-details panel.
    as_indices = [
        i
        for i, ch in enumerate(crp.children)
        if cf.classes[ch.class_index].name == "ActivityScore"
    ]
    if as_indices:
        expected = list(range(as_indices[0], as_indices[-1] + 1))
        if as_indices != expected:
            raise MintError(
                f"ActivityScore children not contiguous in CRP: indices={as_indices}"
            )
        first_as = crp.children[as_indices[0]]
        last_as = crp.children[as_indices[-1]]
        # Parent's count u32 is the 4 bytes immediately before the first
        # AS frame's mark_start.
        count_off = first_as.start - 4
        current_count = struct.unpack_from("<I", section, count_off)[0]
        if current_count != len(as_indices):
            raise MintError(
                f"ActivityScore parent count mismatch: u32@0x{count_off:x}="
                f"{current_count}, child count={len(as_indices)}"
            )
        struct.pack_into("<I", section, count_off, 0)
        del section[first_as.start : last_as.end]
        steps.append(
            f"ActivityScore: {len(as_indices)} record(s) removed, "
            f"parent count u32 (0x{count_off:x}) -> 0"
        )

        # The u32 immediately before the AS count is `3 * chapters_completed`
        # in source proofs (ch2:3, ch3:6, epilogue:9). Suspected driver of the
        # end-screen chapter-progression banner (red icons for completed
        # chapters + X at the death chapter). Zero to suppress carryover.
        banner_off = count_off - 4
        banner_pre = struct.unpack_from("<I", section, banner_off)[0]
        struct.pack_into("<I", section, banner_off, 0)
        steps.append(
            f"chapter-banner u32 (CRP body 0x{banner_off:x}): "
            f"{banner_pre} -> 0"
        )
    else:
        steps.append("ActivityScore: 0 records present (nothing to remove)")

    cf.object_section = bytes(section)
    return MintReport(steps=steps)
