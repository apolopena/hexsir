"""Smoke tests for scafcli CLI."""

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
    assert "scafcli" in result.output


def test_help():
    """CLI --help shows available commands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert_cli_ok(result)
    assert "repo" in result.output
    assert "tool" in result.output
    assert "archive" in result.output
    assert "inspect" in result.output


def test_version_from_pyproject():
    """Version falls back to pyproject.toml when package not installed."""
    runner = CliRunner()
    with patch("cli.pkg_version", side_effect=PackageNotFoundError()):
        result = runner.invoke(cli, ["--version"])
    assert_cli_ok(result)
    assert "scafcli" in result.output
