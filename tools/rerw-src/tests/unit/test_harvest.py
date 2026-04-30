"""Tests for harvest command group."""

from click.testing import CliRunner

from commands.harvest import harvest_group
from test_lib.cli import assert_cli_ok


def test_runs():
    """Group executes without error as a game-assets subcommand."""
    runner = CliRunner()
    result = runner.invoke(harvest_group, [])
    assert_cli_ok(result)


def test_help():
    """Group --help shows description."""
    runner = CliRunner()
    result = runner.invoke(harvest_group, ["--help"])
    assert_cli_ok(result)
