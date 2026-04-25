"""Tests for verify command."""

import zlib

from click.testing import CliRunner

from commands.verify import verify_cmd
from test_lib.cli import assert_cli_ok

DEFAULT_OFFSET = 12


def _create_valid_file(tmp_path, offset=DEFAULT_OFFSET):
    """Create a file with valid CRC32 at given offset."""
    body = b"hello world test data"
    crc = zlib.crc32(body) & 0xFFFFFFFF

    data = bytearray(offset)
    data.extend(crc.to_bytes(4, "little"))
    data.extend(body)

    test_file = tmp_path / "valid.bin"
    test_file.write_bytes(bytes(data))
    return test_file


def _create_invalid_file(tmp_path, offset=DEFAULT_OFFSET):
    """Create a file with wrong CRC32 at given offset."""
    body = b"hello world test data"

    data = bytearray(offset)
    data.extend(b"\x00\x00\x00\x00")
    data.extend(body)

    test_file = tmp_path / "invalid.bin"
    test_file.write_bytes(bytes(data))
    return test_file


def test_verified(tmp_path):
    """Command reports VERIFIED for valid checksum."""
    test_file = _create_valid_file(tmp_path)
    runner = CliRunner()
    result = runner.invoke(verify_cmd, [str(test_file)])
    assert_cli_ok(result)
    assert "VERIFIED" in result.output


def test_verified_custom_offset(tmp_path):
    """Command reports VERIFIED with custom offset."""
    test_file = _create_valid_file(tmp_path, offset=8)
    runner = CliRunner()
    result = runner.invoke(verify_cmd, [str(test_file), "--offset", "8"])
    assert_cli_ok(result)
    assert "VERIFIED" in result.output


def test_baseline_mismatch(tmp_path):
    """Command reports NOT VERIFIED for baseline mismatch."""
    test_file = _create_invalid_file(tmp_path)
    runner = CliRunner()
    result = runner.invoke(verify_cmd, [str(test_file)])
    assert_cli_ok(result)
    assert "NOT VERIFIED" in result.output
    assert "baseline mismatch" in result.output


def test_file_too_small(tmp_path):
    """Command rejects files smaller than needed."""
    test_file = tmp_path / "small.bin"
    test_file.write_bytes(b"0123456789")
    runner = CliRunner()
    result = runner.invoke(verify_cmd, [str(test_file)])
    assert result.exit_code != 0
    assert "too small" in result.output


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(verify_cmd, ["--help"])
    assert_cli_ok(result)
    assert "mismatch" in result.output
