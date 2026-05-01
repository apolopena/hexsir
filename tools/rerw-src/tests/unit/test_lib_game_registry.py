"""Tests for the strict-key game registry.

Covers:
- Bundled YAMLs load cleanly (heroes, magical items, all hero talents).
- Strict lookup rejects unknown keys.
- by_engine_name resolves engine tokens (e.g. "Geppetto" -> entry).
- Schema validation rejects mismatched registry_id / unsupported major.
- Duplicate-key and duplicate-GUID detection in synthetic fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib import game_registry as registry
from lib.game_registry import RegistryError


REPO_ROOT = Path(__file__).resolve().parents[3].parent
DATA_DIR = REPO_ROOT / "tools/rerw-src/data"


# --- Bundled-YAML smoke tests --------------------------------------------


def test_heroes_loads_all_bundled_files() -> None:
    reg = registry.heroes()
    # Sanity: 12 heroes today; at minimum >0 and contains geppetto.
    assert len(reg.entries) >= 1
    assert "geppetto" in reg.entries
    geppetto = reg.entries["geppetto"]
    assert geppetto.engine_name == "Geppetto"
    assert geppetto.save_ref == "Heroes\\Geppetto.herodef.ot"


def test_heroes_lookup_strict() -> None:
    reg = registry.heroes()
    assert reg.lookup("geppetto").key == "geppetto"
    with pytest.raises(RegistryError, match="Unknown hero key"):
        reg.lookup("not_a_hero")


def test_heroes_lookup_by_engine_name() -> None:
    reg = registry.heroes()
    assert reg.lookup_by_engine_name("Geppetto").key == "geppetto"
    with pytest.raises(RegistryError, match="Unknown hero engine name"):
        reg.lookup_by_engine_name("not_a_hero")


def test_hero_talents_loads_for_each_hero() -> None:
    heroes_reg = registry.heroes()
    for hero_key in heroes_reg.entries:
        talents = registry.hero_talents(hero_key)
        # All bundled hero YAMLs have 28 controllers.
        assert len(talents.entries) == 28, (
            f"{hero_key}: expected 28 talents, got {len(talents.entries)}"
        )


def test_hero_talents_lookup_strict() -> None:
    talents = registry.hero_talents("geppetto")
    twin = talents.lookup("TwinDummies")
    assert twin.key == "TwinDummies"
    assert twin.display_name == "Twin Dummies"
    assert len(twin.guid) == 16
    with pytest.raises(RegistryError, match="Unknown talent key"):
        talents.lookup("twin dummies")  # display name, not key


def test_hero_talents_unknown_hero() -> None:
    with pytest.raises(RegistryError, match="Unknown hero key"):
        registry.hero_talents("not_a_hero")


def test_magical_items_loads_bundled() -> None:
    reg = registry.magical_items()
    assert len(reg.entries) >= 1
    assert "Moonstone" in reg.entries
    moon = reg.entries["Moonstone"]
    assert len(moon.guid) == 16
    assert moon.rarity  # populated


def test_magical_items_lookup_strict() -> None:
    reg = registry.magical_items()
    assert reg.lookup("Moonstone").key == "Moonstone"
    with pytest.raises(RegistryError, match="Unknown item key"):
        reg.lookup("moonstone")  # case-mismatch is not a strict key


# --- Synthetic-fixture validation tests ----------------------------------


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_heroes_rejects_wrong_registry_id(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "heroes/geppetto.yaml",
        'schema_version: "1.0.0"\nregistry_id: wrong_id\n'
        "hero:\n  key: geppetto\n  engine_name: Geppetto\n"
        "controllers: []\n",
    )
    with pytest.raises(RegistryError, match="registry_id"):
        registry.heroes(data_dir=tmp_path)


def test_heroes_rejects_unsupported_major(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "heroes/geppetto.yaml",
        'schema_version: "2.0.0"\nregistry_id: hero_talents\n'
        "hero:\n  key: geppetto\n  engine_name: Geppetto\n"
        "controllers: []\n",
    )
    with pytest.raises(RegistryError, match="major"):
        registry.heroes(data_dir=tmp_path)


def test_heroes_rejects_filename_stem_mismatch(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "heroes/wrong_filename.yaml",
        'schema_version: "1.0.0"\nregistry_id: hero_talents\n'
        "hero:\n  key: geppetto\n  engine_name: Geppetto\n"
        "controllers: []\n",
    )
    with pytest.raises(RegistryError, match="filename stem"):
        registry.heroes(data_dir=tmp_path)


def test_hero_talents_rejects_duplicate_key(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "heroes/dummy.yaml",
        'schema_version: "1.0.0"\nregistry_id: hero_talents\n'
        "hero:\n  key: dummy\n  engine_name: Dummy\n"
        "controllers:\n"
        '  - display_name: A\n    key: SameKey\n    controller_name: "C A"\n'
        '    guid: 33cdbac4ce86134da99bc59a19021b6a\n'
        '  - display_name: B\n    key: SameKey\n    controller_name: "C B"\n'
        '    guid: 56e3027d1942924185b86d128135e85e0\n',
    )
    with pytest.raises(RegistryError, match="duplicate talent key"):
        registry.hero_talents("dummy", data_dir=tmp_path)


def test_hero_talents_rejects_duplicate_guid(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "heroes/dummy.yaml",
        'schema_version: "1.0.0"\nregistry_id: hero_talents\n'
        "hero:\n  key: dummy\n  engine_name: Dummy\n"
        "controllers:\n"
        '  - display_name: A\n    key: KeyA\n    controller_name: "C A"\n'
        '    guid: 33cdbac4ce86134da99bc59a19021b6a\n'
        '  - display_name: B\n    key: KeyB\n    controller_name: "C B"\n'
        '    guid: 33cdbac4ce86134da99bc59a19021b6a\n',
    )
    with pytest.raises(RegistryError, match="duplicate talent guid"):
        registry.hero_talents("dummy", data_dir=tmp_path)


def test_magical_items_rejects_duplicate_key(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "magical-items.yaml",
        'schema_version: "1.0.0"\nregistry_id: magical_items\n'
        "items:\n"
        '  - display_name: A\n    key: SameKey\n    effect: e\n    rarity: Common\n'
        '    guid: 26a8cbfceeff0b45bfa274a4c07f6f8a\n'
        '  - display_name: B\n    key: SameKey\n    effect: e\n    rarity: Common\n'
        '    guid: 56e3027d1942924185b86d128135e85e0\n',
    )
    with pytest.raises(RegistryError, match="duplicate item key"):
        registry.magical_items(data_dir=tmp_path)


def test_magical_items_rejects_invalid_guid(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "magical-items.yaml",
        'schema_version: "1.0.0"\nregistry_id: magical_items\n'
        "items:\n"
        '  - display_name: A\n    key: KeyA\n    effect: e\n    rarity: Common\n'
        '    guid: zzzz_not_hex\n',
    )
    with pytest.raises(RegistryError, match="not valid hex"):
        registry.magical_items(data_dir=tmp_path)
