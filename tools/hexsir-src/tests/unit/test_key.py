"""Tests for key command."""

from click.testing import CliRunner

from commands.key import key_cmd
from test_lib.cli import assert_cli_ok


def test_finds_ascii_key(tmp_path):
    """Command finds ASCII key in file."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"\x00\x00hello\x00\x00")

    runner = CliRunner()
    result = runner.invoke(key_cmd, ["hello", "--file", str(test_file)])
    assert_cli_ok(result)
    assert "Key Match" in result.output
    assert "ascii" in result.output


def test_finds_utf16le_key(tmp_path):
    """Command finds UTF-16LE key in file."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"\x00\x00" + "hello".encode("utf-16le") + b"\x00\x00")

    runner = CliRunner()
    result = runner.invoke(key_cmd, ["hello", "--file", str(test_file)])
    assert_cli_ok(result)
    assert "Key Match" in result.output
    assert "utf16le" in result.output


def test_no_match(tmp_path):
    """Command reports no matches when key not found."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"\x00\x01\x02\x03\x04\x05")

    runner = CliRunner()
    result = runner.invoke(key_cmd, ["hello", "--file", str(test_file)])
    assert_cli_ok(result)
    assert "No key matches found" in result.output


def test_env_var_file(tmp_path, monkeypatch):
    """Command reads file from HEXSIR_FILE env var."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"testkey")

    monkeypatch.setenv("HEXSIR_FILE", str(test_file))

    runner = CliRunner()
    result = runner.invoke(key_cmd, ["testkey"])
    assert_cli_ok(result)
    assert "Key Match" in result.output


def test_missing_file():
    """Command errors when no file specified."""
    runner = CliRunner()
    result = runner.invoke(key_cmd, ["hello"])
    assert result.exit_code != 0
    assert "HEXSIR_FILE" in result.output


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(key_cmd, ["--help"])
    assert_cli_ok(result)
