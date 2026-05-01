"""Tests for the mint primitive.

The fixture discovers every `Profile_1.ob` under `rw/saves/proofs/` and
parametrizes each test over all of them. New chapter proofs added to that
directory are picked up automatically -- no per-chapter test functions to
maintain. Tests that need to read field positions that shift with content
(post-vector u32s in the HC body) compute offsets at runtime from
`ingredient_vec_count`, so the same assertions work across chapters.

Two important regressions guard against past mistakes:

1. ActivityScore RECORDS REMOVED, count u32 ZEROED. Earlier mint versions
   either truncated AS bodies (silencer trip) or preserved them verbatim
   (chapter-N icon carryover). The current recipe removes the records
   entirely. See `rw/key-findings/save-silencer-mechanism.md`.

2. Mint must work across chapter shapes. The walker resolves
   `dream_shards_spent` dynamically; an earlier hardcoded +0x35D offset
   only worked for chapter-2 HC bodies and broke chapter-3+.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from lib import cooked
from lib.hc_walker import walk_hc_body
from lib.save_mint import MintConfig, mint_object_section

REPO_ROOT = Path(__file__).resolve().parents[3].parent
PROOFS_ROOT = REPO_ROOT / "rw/saves/proofs"

HC_CLASS = "oCDtEntityCpntHeroControllerPersistentData"
GL_CLASS = "oCDtEntityCpntGroupLevelPersistentData"


def _discover_proofs() -> list[Path]:
    if not PROOFS_ROOT.is_dir():
        return []
    return sorted(PROOFS_ROOT.rglob("Profile_1.ob"))


_DISCOVERED = _discover_proofs()


@pytest.fixture(
    params=_DISCOVERED,
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix() if _DISCOVERED else "no-proofs",
)
def proof_cf(request) -> cooked.CookedFile:
    if not _DISCOVERED:
        pytest.skip(f"no proofs discovered under {PROOFS_ROOT}")
    cf = cooked.parse_file(Path(request.param).read_bytes())
    # The mint operates on chapter-boss-kill proofs: must have an active
    # HeroController instance whose body the walker can resolve (which
    # requires at least one HeroMOPersistentData frame to anchor the
    # unframed-region length). Files under proofs/ that don't satisfy
    # these preconditions (clean / pre-run / unusual debug captures) are
    # skipped rather than failed.
    roots = cooked.parse_object_tree(cf)
    hc_hits = list(cooked.find_class_in_tree(cf, roots, HC_CLASS))
    if not hc_hits:
        pytest.skip(
            f"{request.param.relative_to(REPO_ROOT)} has no {HC_CLASS} "
            "instance (not a chapter-boss-kill proof)"
        )
    hc = hc_hits[0][1]
    hc_body = cf.object_section[hc.start + 8 : hc.end - 4]
    hc_class = next(c for c in cf.classes if c.name == HC_CLASS)
    try:
        walk_hc_body(hc_body, hc.children, hc.start, hc_class.schema_version)
    except RuntimeError as exc:
        pytest.skip(
            f"{request.param.relative_to(REPO_ROOT)} HC body not walkable: {exc}"
        )
    return cf


def _hc(cf: cooked.CookedFile) -> cooked.TreeNode:
    roots = cooked.parse_object_tree(cf)
    return list(cooked.find_class_in_tree(cf, roots, HC_CLASS))[0][1]


def _hc_body(cf: cooked.CookedFile) -> bytes:
    hc = _hc(cf)
    return cf.object_section[hc.start + 8 : hc.end - 4]


def _post_vec_offset(hc_body: bytes) -> int:
    """Byte offset of the first post-ingredient-vector u32 (Raven Feathers
    consumed). Stars of Fate sits at +0x04 from this."""
    vec_count = struct.unpack_from("<I", hc_body, 0x21)[0]
    return 0x25 + 20 * vec_count


def _activity_score_count(cf: cooked.CookedFile) -> int:
    roots = cooked.parse_object_tree(cf)
    return len(list(cooked.find_class_in_tree(cf, roots, "ActivityScore")))


def test_activity_score_records_removed(proof_cf: cooked.CookedFile) -> None:
    """REGRESSION: mint must remove all ActivityScore records.

    Earlier recipes either truncated bodies (silencer trip) or preserved
    them (chapter-N icon carryover). The fix is to remove the records
    entirely so the deserialize loop runs zero iterations.
    """
    before = _activity_score_count(proof_cf)
    assert before > 0, "fixture has no ActivityScore records to remove"

    mint_object_section(proof_cf, MintConfig())
    after = _activity_score_count(proof_cf)

    assert after == 0, f"expected 0 ActivityScore records after mint, got {after}"


def test_activity_score_parent_count_zeroed(proof_cf: cooked.CookedFile) -> None:
    """The CRP body's u32 just before the first AS frame is the count read
    by the deserialize loop. After mint it must be 0 (otherwise the loop
    tries to read N frames that no longer exist).
    """
    mint_object_section(proof_cf, MintConfig())

    roots_after = cooked.parse_object_tree(proof_cf)
    crp_after = cooked.find_class_in_tree(
        proof_cf, roots_after, "oCDtCurrentRunProfileData"
    )[0][1]
    # Locate the count u32 by walking from CRP body start to HSD start.
    # After AS removal, CRP's last child is HeroScoreData and the AS count
    # u32 sits at HSD.start - 4.
    hsd = next(
        ch
        for ch in crp_after.children
        if proof_cf.classes[ch.class_index].name == "HeroScoreData"
    )
    count = struct.unpack_from("<I", proof_cf.object_section, hsd.start - 4)[0]
    assert count == 0, f"AS parent count u32 should be 0 after mint, got {count}"


def test_mint_zeros_damage_floats(proof_cf: cooked.CookedFile) -> None:
    mint_object_section(proof_cf, MintConfig())
    assert _hc_body(proof_cf)[0x11:0x21] == b"\x00" * 16, (
        "HC damage floats not zeroed"
    )


def test_mint_sets_stars_of_fate(proof_cf: cooked.CookedFile) -> None:
    """Stars of Fate sits at HC body+0x04 past the post-vector base
    (which itself depends on ingredient_vec_count)."""
    pv = _post_vec_offset(_hc_body(proof_cf))

    mint_object_section(proof_cf, MintConfig(stars_of_fate=42))

    body = _hc_body(proof_cf)
    (stars,) = struct.unpack_from("<I", body, pv + 0x04)
    assert stars == 42


def test_mint_zeros_feathers_consumed(proof_cf: cooked.CookedFile) -> None:
    """Raven Feathers consumed is the first u32 after the ingredient vector."""
    pv = _post_vec_offset(_hc_body(proof_cf))

    mint_object_section(proof_cf, MintConfig())

    body = _hc_body(proof_cf)
    feathers = struct.unpack_from("<I", body, pv)[0]
    assert feathers == 0, f"feathers_consumed should be 0 after mint, got {feathers}"


def test_mint_sets_hero_level_and_xp(proof_cf: cooked.CookedFile) -> None:
    mint_object_section(proof_cf, MintConfig(hero_level=1, hero_xp=0))
    roots = cooked.parse_object_tree(proof_cf)
    _, gl = list(cooked.find_class_in_tree(proof_cf, roots, GL_CLASS))[0]
    body = proof_cf.object_section[gl.start + 8 : gl.end - 4]
    (level,) = struct.unpack_from("<I", body, 0x11)
    (xp,) = struct.unpack_from("<I", body, 0x15)
    assert level == 1
    assert xp == 0


def test_mint_skips_stars_when_none(proof_cf: cooked.CookedFile) -> None:
    """stars_of_fate=None must not modify the stars u32."""
    pv = _post_vec_offset(_hc_body(proof_cf))
    (stars_before,) = struct.unpack_from("<I", _hc_body(proof_cf), pv + 0x04)

    mint_object_section(proof_cf, MintConfig(stars_of_fate=None))

    (stars_after,) = struct.unpack_from("<I", _hc_body(proof_cf), pv + 0x04)
    assert stars_after == stars_before


def test_mint_output_round_trips(proof_cf: cooked.CookedFile) -> None:
    """The minted file must encode + parse cleanly (catches malformed bodies
    that survived the tree walker but corrupt the stream).
    """
    mint_object_section(proof_cf, MintConfig())
    out = cooked.encode_file(proof_cf)
    cf2 = cooked.parse_file(out)
    cooked.parse_object_tree(cf2)  # raises on malformed bodies
    assert _activity_score_count(cf2) == 0
