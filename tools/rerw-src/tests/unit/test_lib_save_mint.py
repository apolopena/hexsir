"""Tests for the mint primitive.

The fixture discovers every `Profile_1.ob` under `rw/saves/proofs/` and
parametrizes each test over all of them. New chapter proofs added to that
directory are picked up automatically -- no per-chapter test functions to
maintain. Tests that need to read field positions that shift with content
(post-vector u32s in the HC body) compute offsets at runtime, so the
same assertions work across chapters.

Two important regressions guard against past mistakes:

1. ActivityScore RECORDS REMOVED, count u32 ZEROED. Earlier mint versions
   either truncated AS bodies (silencer trip) or preserved them verbatim
   (chapter-N icon carryover). The current recipe removes the records
   entirely. See `rw/findings/save-silencer-mechanism.md`.

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
from lib.save_mint import mint_object_section

REPO_ROOT = Path(__file__).resolve().parents[3].parent
PROOFS_ROOT = REPO_ROOT / "rw/saves/proofs"

HC_CLASS = "oCDtEntityCpntHeroControllerPersistentData"
GL_CLASS = "oCDtEntityCpntGroupLevelPersistentData"
CRP_CLASS = "oCDtCurrentRunProfileData"


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
    vec_count = struct.unpack_from("<I", hc_body, 0x21)[0]
    return 0x25 + 20 * vec_count


def _activity_score_count(cf: cooked.CookedFile) -> int:
    roots = cooked.parse_object_tree(cf)
    return len(list(cooked.find_class_in_tree(cf, roots, "ActivityScore")))


# --- Behavioral regressions ----------------------------------------------


def test_activity_score_records_removed(proof_cf: cooked.CookedFile) -> None:
    """REGRESSION: mint must remove all ActivityScore records.

    Earlier recipes either truncated bodies (silencer trip) or preserved
    them (chapter-N icon carryover). The fix is to remove the records
    entirely so the deserialize loop runs zero iterations.
    """
    before = _activity_score_count(proof_cf)
    assert before > 0, "fixture has no ActivityScore records to remove"

    mint_object_section(proof_cf)
    after = _activity_score_count(proof_cf)

    assert after == 0, f"expected 0 ActivityScore records after mint, got {after}"


def test_activity_score_parent_count_zeroed(proof_cf: cooked.CookedFile) -> None:
    """The CRP body's u32 just before the first AS frame is the count read
    by the deserialize loop. After mint it must be 0.
    """
    mint_object_section(proof_cf)

    roots_after = cooked.parse_object_tree(proof_cf)
    crp_after = cooked.find_class_in_tree(proof_cf, roots_after, CRP_CLASS)[0][1]
    hsd = next(
        ch
        for ch in crp_after.children
        if proof_cf.classes[ch.class_index].name == "HeroScoreData"
    )
    count = struct.unpack_from("<I", proof_cf.object_section, hsd.start - 4)[0]
    assert count == 0, f"AS parent count u32 should be 0 after mint, got {count}"


def test_chapter_banner_zeroed(proof_cf: cooked.CookedFile) -> None:
    """The CRP body u32 immediately preceding the AS-count u32 (the
    chapter-progression banner driver) must be 0 after mint.
    """
    # Capture the banner u32 location before mint snips AS records.
    roots_before = cooked.parse_object_tree(proof_cf)
    crp_before = cooked.find_class_in_tree(proof_cf, roots_before, CRP_CLASS)[0][1]
    as_children = [
        ch
        for ch in crp_before.children
        if proof_cf.classes[ch.class_index].name == "ActivityScore"
    ]
    assert as_children, "fixture's CRP has no AS children"
    banner_off_in_section = as_children[0].start - 8

    mint_object_section(proof_cf)

    # After AS removal, those bytes shifted out, but the banner u32 was
    # written to 0 by the setter before the removal step. Locate via the
    # remaining CRP children: the banner u32 sits at HSD.start - 8.
    roots_after = cooked.parse_object_tree(proof_cf)
    crp_after = cooked.find_class_in_tree(proof_cf, roots_after, CRP_CLASS)[0][1]
    hsd = next(
        ch
        for ch in crp_after.children
        if proof_cf.classes[ch.class_index].name == "HeroScoreData"
    )
    banner = struct.unpack_from("<I", proof_cf.object_section, hsd.start - 8)[0]
    assert banner == 0, f"chapter-banner u32 should be 0 after mint, got {banner}"


def test_held_feathers_zeroed(proof_cf: cooked.CookedFile) -> None:
    """Held Raven Feathers (CRP body+0x15D) must be 0 after mint."""
    mint_object_section(proof_cf)
    roots = cooked.parse_object_tree(proof_cf)
    crp = cooked.find_class_in_tree(proof_cf, roots, CRP_CLASS)[0][1]
    feathers = struct.unpack_from(
        "<I", proof_cf.object_section, crp.start + 8 + 0x15D
    )[0]
    assert feathers == 0, f"held feathers should be 0 after mint, got {feathers}"


def test_mint_zeros_per_run_float_block(proof_cf: cooked.CookedFile) -> None:
    """HC body+0x11..+0x21 covers two unidentified floats followed by
    dream_shards_earned (+0x19) and held_dream_shards (+0x1D). Mint zeros
    the whole 16-byte block."""
    mint_object_section(proof_cf)
    assert _hc_body(proof_cf)[0x11:0x21] == b"\x00" * 16, (
        "HC per-run float block not zeroed"
    )


def test_mint_zeros_held_dream_shards(proof_cf: cooked.CookedFile) -> None:
    """Held Dream Shards (HC body+0x1D, float32) must be 0.0 after mint."""
    mint_object_section(proof_cf)
    held = struct.unpack_from("<f", _hc_body(proof_cf), 0x1D)[0]
    assert held == 0.0, f"held dream shards should be 0 after mint, got {held}"


def test_mint_zeros_stars(proof_cf: cooked.CookedFile) -> None:
    """Per the new mint design, Stars of Fate is unconditionally zeroed.
    Customize via `rerw write savefile stars <n>` after mint.
    """
    pv = _post_vec_offset(_hc_body(proof_cf))
    mint_object_section(proof_cf)
    body = _hc_body(proof_cf)
    (stars,) = struct.unpack_from("<I", body, pv + 0x04)
    assert stars == 0, f"stars should be 0 after mint, got {stars}"


def test_mint_zeros_feathers_spent(proof_cf: cooked.CookedFile) -> None:
    """The per-run "Raven Feathers consumed" stat (HC body post-vec+0x00)."""
    pv = _post_vec_offset(_hc_body(proof_cf))
    mint_object_section(proof_cf)
    body = _hc_body(proof_cf)
    feathers_spent = struct.unpack_from("<I", body, pv)[0]
    assert feathers_spent == 0


def test_mint_sets_level_and_xp(proof_cf: cooked.CookedFile) -> None:
    mint_object_section(proof_cf)
    roots = cooked.parse_object_tree(proof_cf)
    _, gl = list(cooked.find_class_in_tree(proof_cf, roots, GL_CLASS))[0]
    body = proof_cf.object_section[gl.start + 8 : gl.end - 4]
    (level,) = struct.unpack_from("<I", body, 0x11)
    (xp,) = struct.unpack_from("<I", body, 0x15)
    assert level == 1
    assert xp == 0


def test_mint_output_round_trips(proof_cf: cooked.CookedFile) -> None:
    """The minted file must encode + parse cleanly (catches malformed bodies
    that survived the tree walker but corrupt the stream).
    """
    mint_object_section(proof_cf)
    out = cooked.encode_file(proof_cf)
    cf2 = cooked.parse_file(out)
    cooked.parse_object_tree(cf2)  # raises on malformed bodies
    assert _activity_score_count(cf2) == 0
