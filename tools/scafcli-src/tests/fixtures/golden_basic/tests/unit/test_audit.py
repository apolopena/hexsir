"""Tests for audit command."""

from click.testing import CliRunner
from commands.audit import audit_cmd
from test_lib.cli import assert_cli_ok


def test_runs():
    """Command executes without error."""
    runner = CliRunner()
    result = runner.invoke(audit_cmd, [])
    assert_cli_ok(result)


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(audit_cmd, ["--help"])
    assert_cli_ok(result)
