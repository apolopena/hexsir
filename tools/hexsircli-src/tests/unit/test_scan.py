"""Tests for scan command."""

from click.testing import CliRunner

from commands.scan import scan_cmd
from test_lib.cli import assert_cli_ok


def test_runs(tmp_path):
    """Command executes without error."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b")

    runner = CliRunner()
    result = runner.invoke(scan_cmd, [str(test_file), "--stop", "4"])
    assert_cli_ok(result)


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(scan_cmd, ["--help"])
    assert_cli_ok(result)
