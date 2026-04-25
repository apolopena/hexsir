"""Smoke tests for hexsir CLI."""

from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from click.testing import CliRunner
from cli import cli
from test_lib.cli import assert_cli_ok


def test_version():
    """CLI --version flag prints version string."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert_cli_ok(result)
    assert "hexsir" in result.output


def test_help():
    """CLI --help shows available groups and commands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert_cli_ok(result)
    assert "checksum" in result.output
    assert "probe" in result.output
    assert "mint" in result.output


def test_checksum_group_help():
    """Checksum group shows its subcommands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["checksum", "--help"])
    assert_cli_ok(result)
    assert "basic" in result.output
    assert "header" in result.output
    assert "scan" in result.output
    assert "verify" in result.output


def test_probe_group_help():
    """Probe group shows its subcommands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["probe", "--help"])
    assert_cli_ok(result)
    assert "key" in result.output
    assert "delimiter" in result.output


def test_version_from_pyproject():
    """Version falls back to pyproject.toml when package not installed."""
    runner = CliRunner()
    with patch("cli.pkg_version", side_effect=PackageNotFoundError()):
        result = runner.invoke(cli, ["--version"])
    assert_cli_ok(result)
    assert "hexsir" in result.output
