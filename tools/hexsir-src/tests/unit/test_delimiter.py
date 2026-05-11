"""Tests for delimiter command."""

from click.testing import CliRunner

from commands.delimiter import delimiter_cmd
from test_lib.cli import assert_cli_ok


def test_finds_equals_delimiter(tmp_path):
    """Command finds equals delimiter at offset."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"key=value")

    runner = CliRunner()
    result = runner.invoke(
        delimiter_cmd,
        ["--file", str(test_file), "--after", "3", "--encoding", "ascii"],
    )
    assert_cli_ok(result)
    assert "Delimiter Match" in result.output
    assert "'='" in result.output


def test_finds_null_delimiter(tmp_path):
    """Command finds null byte delimiter."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"key\x00value")

    runner = CliRunner()
    result = runner.invoke(
        delimiter_cmd,
        ["--file", str(test_file), "--after", "3", "--encoding", "ascii"],
    )
    assert_cli_ok(result)
    assert "Delimiter Match" in result.output


def test_no_match(tmp_path):
    """Command reports no matches when delimiter not found."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"keyXvalue")

    runner = CliRunner()
    result = runner.invoke(
        delimiter_cmd,
        ["--file", str(test_file), "--after", "3", "--encoding", "ascii"],
    )
    assert_cli_ok(result)
    assert "No delimiter matches found" in result.output


def test_env_var_file(tmp_path, monkeypatch):
    """Command reads file from HEXSIR_FILE env var."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"key=value")

    monkeypatch.setenv("HEXSIR_FILE", str(test_file))

    runner = CliRunner()
    result = runner.invoke(
        delimiter_cmd,
        ["--after", "3", "--encoding", "ascii"],
    )
    assert_cli_ok(result)
    assert "Delimiter Match" in result.output


def test_offset_out_of_bounds(tmp_path):
    """Command errors when offset out of bounds."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"short")

    runner = CliRunner()
    result = runner.invoke(
        delimiter_cmd,
        ["--file", str(test_file), "--after", "100", "--encoding", "ascii"],
    )
    assert result.exit_code != 0
    assert "outside file bounds" in result.output


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(delimiter_cmd, ["--help"])
    assert_cli_ok(result)
