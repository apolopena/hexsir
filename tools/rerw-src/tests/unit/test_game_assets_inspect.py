"""Tests for `rerw game-assets inspect` discovery commands."""

from __future__ import annotations

from click.testing import CliRunner

from commands.game_assets_inspect import heroes_cmd, items_cmd, talents_cmd


def test_inspect_heroes_default() -> None:
    runner = CliRunner()
    result = runner.invoke(heroes_cmd, [])
    assert result.exit_code == 0, result.output
    # Heroes default fields are NAME / KEY only.
    assert "NAME: Geppetto" in result.output
    assert "KEY: geppetto" in result.output
    # Verbose-only fields must not appear in default mode.
    assert "SAVE_REF" not in result.output
    assert "YAML" not in result.output


def test_inspect_heroes_verbose() -> None:
    runner = CliRunner()
    result = runner.invoke(heroes_cmd, ["-v"])
    assert result.exit_code == 0, result.output
    assert "SAVE_REF: Heroes\\Geppetto.herodef.ot" in result.output
    assert "YAML:" in result.output


def test_inspect_talents_default() -> None:
    runner = CliRunner()
    result = runner.invoke(talents_cmd, ["--for-hero", "geppetto"])
    assert result.exit_code == 0, result.output
    assert "NAME: Twin Dummies" in result.output
    assert "KEY: TwinDummies" in result.output
    assert "DESCRIPTION:" in result.output
    # Verbose-only fields must not appear.
    assert "GUID:" not in result.output
    assert "CONTROLLER:" not in result.output


def test_inspect_talents_no_description() -> None:
    runner = CliRunner()
    result = runner.invoke(
        talents_cmd, ["--for-hero", "geppetto", "-n"]
    )
    assert result.exit_code == 0, result.output
    assert "KEY: TwinDummies" in result.output
    assert "DESCRIPTION:" not in result.output


def test_inspect_talents_verbose() -> None:
    runner = CliRunner()
    result = runner.invoke(
        talents_cmd, ["--for-hero", "geppetto", "-v"]
    )
    assert result.exit_code == 0, result.output
    assert "GUID: 33cdbac4ce86134da99bc59a19021b6a" in result.output
    assert "CONTROLLER: Skill Controller Trait Twins" in result.output
    assert "IS_START:" in result.output
    assert "IS_ULT:" in result.output


def test_inspect_talents_unknown_hero_errors() -> None:
    runner = CliRunner()
    result = runner.invoke(talents_cmd, ["--for-hero", "not_a_hero"])
    assert result.exit_code != 0
    assert "Unknown hero key" in result.output


def test_inspect_talents_requires_for_hero() -> None:
    runner = CliRunner()
    result = runner.invoke(talents_cmd, [])
    assert result.exit_code != 0
    assert "--for-hero" in result.output or "Missing option" in result.output


def test_inspect_items_default() -> None:
    runner = CliRunner()
    result = runner.invoke(items_cmd, [])
    assert result.exit_code == 0, result.output
    assert "NAME: Moonstone" in result.output
    assert "KEY: Moonstone" in result.output
    assert "DESCRIPTION:" in result.output
    assert "GUID:" not in result.output
    assert "RARITY:" not in result.output


def test_inspect_items_no_description() -> None:
    runner = CliRunner()
    result = runner.invoke(items_cmd, ["-n"])
    assert result.exit_code == 0, result.output
    assert "KEY: Moonstone" in result.output
    assert "DESCRIPTION:" not in result.output


def test_inspect_items_verbose() -> None:
    runner = CliRunner()
    result = runner.invoke(items_cmd, ["-v"])
    assert result.exit_code == 0, result.output
    assert "GUID: 26a8cbfceeff0b45bfa274a4c07f6f8a" in result.output
    assert "RARITY: Common" in result.output
    assert "EFFECT:" in result.output
