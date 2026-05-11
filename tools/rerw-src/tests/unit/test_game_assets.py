"""Tests for `rerw game-assets` commands."""

from pathlib import Path

from click.testing import CliRunner

from commands.game_assets import game_assets_group
from test_lib.cli import assert_cli_ok


def _cooked_tree(tmp_path: Path) -> Path:
    cooked = tmp_path / "Ravenswatch" / "DarkTalesResources" / "_Cooking"
    scenery = cooked / "3N" / "Fbqzqus"
    scenery.mkdir(parents=True)
    (scenery / "BgagCgyg").mkdir()
    (scenery / ".ndttqz").touch()
    (scenery / "BgagCgyg!Arwvq_Fxgll_Sgujqi.hap.Kqrxqius.yqz").touch()
    (scenery / "Srxxrz!Wligu_Oh_Aqurqv.hap.Kqrxqius.yqz").touch()
    return cooked


def test_ls_lists_decoded_children(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        game_assets_group,
        ["ls", "3D/Scenery", "--cooking-root", str(cooked)],
    )
    assert_cli_ok(result)
    assert "BabaYaga" in result.output
    assert "Common!Altar_Of_Heroes.fbx.Geometry.gen" in result.output


def test_ls_full_path_query_returns_full_paths(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    runner = CliRunner()
    result = runner.invoke(game_assets_group, ["ls", str(cooked / "3D" / "Scenery")])
    assert_cli_ok(result)

    lines = result.output.splitlines()
    assert lines
    assert all(line.startswith(cooked.as_posix()) for line in lines)
    assert (cooked / "3D" / "Scenery" / "BabaYaga").as_posix() in lines
    assert (
        cooked / "3D" / "Scenery" / "Common!Altar_Of_Heroes.fbx.Geometry.gen"
    ).as_posix() in lines


def test_ls_full_ciphered_path_query_returns_full_paths(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    runner = CliRunner()
    result = runner.invoke(game_assets_group, ["ls", str(cooked / "3N" / "Fbqzqus")])
    assert_cli_ok(result)

    lines = result.output.splitlines()
    assert lines
    assert all(line.startswith(cooked.as_posix()) for line in lines)
    assert (cooked / "3D" / "Scenery" / "BabaYaga").as_posix() in lines


def test_ls_raw_keeps_on_disk_ciphered_paths(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        game_assets_group,
        ["ls", "--raw", str(cooked / "3N" / "Fbqzqus")],
    )
    assert_cli_ok(result)
    assert (cooked / "3N" / "Fbqzqus" / "BgagCgyg").as_posix() in result.output


def test_ls_cooked_relative_truncates_full_prefix(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        game_assets_group,
        ["ls", "--cooked-relative", str(cooked / "3D" / "Scenery")],
    )
    assert_cli_ok(result)
    assert "3D/Scenery/BabaYaga" in result.output
    assert cooked.as_posix() not in result.output


def test_ls_truncate_prefix_keeps_short_install_context(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        game_assets_group,
        ["ls", "--truncate-paths", str(cooked / "3D" / "Scenery")],
    )
    assert_cli_ok(result)
    assert "/tmp/.../DarkTalesResources/_Cooking/3D/Scenery/BabaYaga" in result.output
    assert cooked.as_posix() not in result.output


def test_ls_short_t_truncates_paths(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        game_assets_group,
        ["ls", "-t", str(cooked / "3D" / "Scenery")],
    )
    assert_cli_ok(result)
    assert "/tmp/.../DarkTalesResources/_Cooking/3D/Scenery/BabaYaga" in result.output


def test_ls_combined_la_flags(tmp_path: Path):
    cooked = _cooked_tree(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        game_assets_group,
        ["ls", "-la", "--cooked-relative", str(cooked / "3D" / "Scenery")],
    )
    assert_cli_ok(result)
    assert "3D/Scenery/.hidden" in result.output
    assert "3D/Scenery/BabaYaga" in result.output
    assert result.output.splitlines()[0].startswith("-") or result.output.splitlines()[
        0
    ].startswith("d")


def test_ls_invalid_full_path_errors(tmp_path: Path):
    cooked = tmp_path / "wrong" / "DarkTalesResources" / "_Cooking"
    runner = CliRunner()
    result = runner.invoke(game_assets_group, ["ls", str(cooked / "3D" / "Scenery")])
    assert result.exit_code != 0
    assert "cooked asset root not found" in result.output


def test_harvest_moved_under_game_assets():
    runner = CliRunner()
    result = runner.invoke(game_assets_group, ["harvest"])
    assert_cli_ok(result)
    assert "harvest" in result.output.lower()


def test_help_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(game_assets_group, ["--help"])
    assert_cli_ok(result)
    assert "ls" in result.output
    assert "harvest" in result.output
