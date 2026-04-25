"""Tests for cipher command."""

from click.testing import CliRunner

from commands.cipher import cipher_cmd
from test_lib.cli import assert_cli_ok


def test_runs():
    """Command executes without error."""
    runner = CliRunner()
    result = runner.invoke(cipher_cmd, ["Geppetto"])
    assert_cli_ok(result)
    assert "Kqjjqiir" in result.output


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(cipher_cmd, ["--help"])
    assert_cli_ok(result)
