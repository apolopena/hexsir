"""Tests for basic command."""

from click.testing import CliRunner

from commands.basic import basic_cmd
from test_lib.cli import assert_cli_ok


def test_runs(tmp_path):
    """Command executes without error."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"\x00\x01\x02\x03\x04\x05\x06\x07")

    runner = CliRunner()
    result = runner.invoke(basic_cmd, [str(test_file)])
    assert_cli_ok(result)


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(basic_cmd, ["--help"])
    assert_cli_ok(result)
