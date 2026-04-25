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


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(decipher_cmd, ["--help"])
    assert_cli_ok(result)
