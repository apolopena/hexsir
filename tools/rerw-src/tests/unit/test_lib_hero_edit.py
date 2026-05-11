"""Tests for the hero-edit primitive.

The strongest validation is byte-equality against the four verified-working
hero-swap goldens under `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/`.
Those goldens were produced by the one-off script that shipped with MAINT-8
and were verified end-to-end in-game (load identity + run state preserved).
Reproducing them byte-for-byte through `swap_hero + recompute_crc` proves the
production primitive matches the verified-working bytes for all three shift
cases (no shift, shrink, grow).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.hero_edit import HeroEditError, find_hero_record, swap_hero
from lib.save_edit import recompute_crc

REPO_ROOT = Path(__file__).resolve().parents[3].parent
SOURCE_PROOF = (
    REPO_ROOT / "rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob"
)
GOLDEN_DIR = (
    REPO_ROOT / "rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1"
)


@pytest.fixture
def source_bytes() -> bytes:
    if not SOURCE_PROOF.is_file():
        pytest.skip(f"Source proof missing: {SOURCE_PROOF}")
    return SOURCE_PROOF.read_bytes()


def _golden(name: str) -> bytes:
    path = GOLDEN_DIR / f"hero-swap-to-{name}" / "Profile_1.ob"
    if not path.is_file():
        pytest.skip(f"Golden missing: {path}")
    return path.read_bytes()


def test_find_hero_record_in_source(source_bytes: bytes) -> None:
    prefix_off, path_off, engine_name = find_hero_record(source_bytes)
    assert engine_name == "Geppetto"
    # Length prefix is the 4 bytes immediately before the path.
    assert path_off - prefix_off == 4
    # 18 + len('Geppetto') = 26.
    expected_len = len(b"Heroes\\Geppetto.herodef.ot")
    assert expected_len == 26
    # Verify the prefix u32 actually holds 26.
    assert (
        int.from_bytes(source_bytes[prefix_off : prefix_off + 4], "little")
        == expected_len
    )


def test_find_hero_record_missing_raises() -> None:
    with pytest.raises(HeroEditError, match="not found"):
        find_hero_record(b"\x00" * 1024)


def test_swap_hero_rejects_malformed_save_ref(source_bytes: bytes) -> None:
    data = bytearray(source_bytes)
    with pytest.raises(HeroEditError, match="does not match"):
        swap_hero(data, "NotAHeroPath")


def test_swap_hero_rejects_wrong_extension(source_bytes: bytes) -> None:
    data = bytearray(source_bytes)
    with pytest.raises(HeroEditError, match="does not match"):
        swap_hero(data, "Heroes\\Carmilla.wrong.ot")


@pytest.mark.parametrize(
    ("engine_name", "expected_size_delta"),
    [
        ("Carmilla", 0),  # 8 chars same as Geppetto
        ("Aladdin", -1),  # 7 chars
        ("Snow_Queen", +2),  # 10 chars
        ("Red", -5),  # 3 chars
    ],
)
def test_swap_hero_matches_verified_golden(
    source_bytes: bytes, engine_name: str, expected_size_delta: int
) -> None:
    """Reproduce each verified-working hero-swap golden byte-for-byte.

    The four goldens cover the full shift range tested in MAINT-8: same-length
    drop-in, shrink, and grow.
    """
    data = bytearray(source_bytes)
    save_ref = f"Heroes\\{engine_name}.herodef.ot"

    old_name, new_name = swap_hero(data, save_ref)
    recompute_crc(data)

    assert old_name == "Geppetto"
    assert new_name == engine_name
    assert len(data) == len(source_bytes) + expected_size_delta

    golden = _golden(engine_name.lower())
    assert bytes(data) == golden, (
        f"Swap output for {engine_name} does not match verified golden "
        f"hero-swap-to-{engine_name.lower()}/Profile_1.ob"
    )


def test_swap_hero_round_trip_back_to_geppetto(source_bytes: bytes) -> None:
    """Geppetto -> Carmilla -> Geppetto should return to the original bytes
    (modulo CRC, which is recomputed identically at each step)."""
    data = bytearray(source_bytes)
    swap_hero(data, "Heroes\\Carmilla.herodef.ot")
    recompute_crc(data)
    swap_hero(data, "Heroes\\Geppetto.herodef.ot")
    recompute_crc(data)
    assert bytes(data) == source_bytes
