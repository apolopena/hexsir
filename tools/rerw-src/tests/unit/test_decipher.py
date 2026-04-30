"""Tests for decipher command."""

from click.testing import CliRunner

from commands.decipher import decipher_cmd
from test_lib.cli import assert_cli_ok


def test_runs():
    """Command executes without error."""
    runner = CliRunner()
    result = runner.invoke(decipher_cmd, ["Kqjjqiir"])
    assert_cli_ok(result)
    assert "Geppetto" in result.output


def test_path_aware_preserves_prefix():
    runner = CliRunner()
    result = runner.invoke(
        decipher_cmd,
        [
            "--path-aware",
            "/mnt/d/steam-storage/steamapps/common/Ravenswatch/"
            "DarkTalesResources/_Cooking/3N/Fbqzqus/"
            "BgagCgyg!Arwvq_Fxgll_Sgujqi.hap.Kqrxqius.yqz",
        ],
    )
    assert_cli_ok(result)
    assert "/mnt/d/steam-storage/steamapps/common/Ravenswatch/" in result.output
    assert "DarkTalesResources/_Cooking/3D/Scenery/" in result.output
    assert "BabaYaga!House_Small_Carpet.fbx.Geometry.gen" in result.output


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(decipher_cmd, ["--help"])
    assert_cli_ok(result)
    assert "--path-aware" in result.output
