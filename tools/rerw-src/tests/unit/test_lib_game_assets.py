"""Tests for cooked game asset helpers."""

from pathlib import Path

import pytest

from lib.game_assets import list_game_assets, normalize_asset_query


def _cooked_tree(tmp_path: Path) -> Path:
    cooked = tmp_path / "Ravenswatch" / "DarkTalesResources" / "_Cooking"
    scenery = cooked / "3N" / "Fbqzqus"
    heroes = cooked / "MzidisFqiidzyv" / "Aqurqv"
    settings = cooked / "VZ" / "Fqiidzyv"
    scenery.mkdir(parents=True)
    heroes.mkdir(parents=True)
    settings.mkdir(parents=True)
    (scenery / "BgagCgyg").mkdir()
    (scenery / ".ndttqz").touch()
    (scenery / "BgagCgyg!Arwvq_Fxgll_Sgujqi.hap.Kqrxqius.yqz").touch()
    (scenery / "Srxxrz!Wligu_Oh_Aqurqv.hap.Kqrxqius.yqz").touch()
    (
        heroes
        / "Aqur_Kqjjqiir!Aqur_Kqjjqiir_Twjjqi.qzidis.ri.MzidisFqiidzyvLqvrwubq.yqz"
    ).touch()
    (settings / "Wkglrz!Wxadqzi_Wvnqv.khp.ri.FbnqtwlqtDhpFqiidzyv.yqz").touch()
    return cooked


def test_normalize_asset_query_handles_full_and_harvested_paths():
    assert (
        normalize_asset_query(
            "/mnt/d/x/DarkTalesResources/_Cooking/3D/Scenery/"
        )
        == "3D/Scenery"
    )
    assert (
        normalize_asset_query(
            "rw/harvested/EntitySettings/Heroes/Hero_Geppetto.entity.ot"
        )
        == "EntitySettings/Heroes/Hero_Geppetto.entity.ot"
    )


def test_list_decoded_children_from_relative_path(tmp_path: Path):
    entries = list_game_assets("3D/Scenery", cooking_root=_cooked_tree(tmp_path))
    assert entries == [
        "BabaYaga",
        "BabaYaga!House_Small_Carpet.fbx.Geometry.gen",
        "Common!Altar_Of_Heroes.fbx.Geometry.gen",
    ]


def test_list_decoded_children_from_full_path(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    entries = list_game_assets(str(cooked / "3D" / "Scenery"))
    assert entries == [
        "BabaYaga",
        "BabaYaga!House_Small_Carpet.fbx.Geometry.gen",
        "Common!Altar_Of_Heroes.fbx.Geometry.gen",
    ]


def test_list_full_and_raw(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    entries = list_game_assets("3D/Scenery", cooking_root=cooked, raw=True, full=True)
    assert entries[0].startswith(cooked.as_posix())
    assert entries[0].endswith("DarkTalesResources/_Cooking/3N/Fbqzqus/BgagCgyg")


def test_list_cooked_relative_truncates_full_prefix(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    entries = list_game_assets(
        str(cooked / "3D" / "Scenery"),
        cooked_relative=True,
    )
    assert entries == [
        "3D/Scenery/BabaYaga",
        "3D/Scenery/BabaYaga!House_Small_Carpet.fbx.Geometry.gen",
        "3D/Scenery/Common!Altar_Of_Heroes.fbx.Geometry.gen",
    ]


def test_list_truncate_prefix_keeps_install_context(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    entries = list_game_assets(
        str(cooked / "3D" / "Scenery"),
        truncate_prefix=True,
    )
    assert entries == [
        "/tmp/.../DarkTalesResources/_Cooking/3D/Scenery/BabaYaga",
        "/tmp/.../DarkTalesResources/_Cooking/3D/Scenery/"
        "BabaYaga!House_Small_Carpet.fbx.Geometry.gen",
        "/tmp/.../DarkTalesResources/_Cooking/3D/Scenery/"
        "Common!Altar_Of_Heroes.fbx.Geometry.gen",
    ]


def test_list_hidden_entries_only_with_all(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    assert ".hidden" not in list_game_assets("3D/Scenery", cooking_root=cooked)
    assert ".hidden" in list_game_assets(
        "3D/Scenery",
        cooking_root=cooked,
        include_hidden=True,
    )


def test_list_long_format_includes_mode_size_and_name(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    entries = list_game_assets(
        "3D/Scenery",
        cooking_root=cooked,
        cooked_relative=True,
        long=True,
    )
    assert entries[0].startswith("d")
    assert entries[0].endswith("3D/Scenery/BabaYaga")


def test_list_ciphered_query(tmp_path: Path):
    entries = list_game_assets(
        "MzidisFqiidzyv/Aqurqv",
        cooking_root=_cooked_tree(tmp_path),
        query_is_ciphered=True,
    )
    assert entries == [
        "Hero_Geppetto!Hero_Geppetto_Puppet.entity.ot.EntitySettingsResource.gen"
    ]


def test_list_auto_detects_ciphered_query(tmp_path: Path):
    entries = list_game_assets(
        "MzidisFqiidzyv/Aqurqv",
        cooking_root=_cooked_tree(tmp_path),
    )
    assert entries == [
        "Hero_Geppetto!Hero_Geppetto_Puppet.entity.ot.EntitySettingsResource.gen"
    ]


def test_list_resolves_decoded_uppercase_z_path(tmp_path: Path):
    entries = list_game_assets("FZ/Settings", cooking_root=_cooked_tree(tmp_path))
    assert entries == [
        "Avalon!Ambient_Ashes.vfx.ot.ScheduledVfxSettings.gen",
    ]


def test_list_invalid_path_errors(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    with pytest.raises(FileNotFoundError, match="asset path not found"):
        list_game_assets("3D/Missing", cooking_root=cooked)
