"""Tests for mint command."""

import zlib

from click.testing import CliRunner

from commands.mint import mint_cmd
from test_lib.cli import assert_cli_ok


def _create_file_with_checksum(tmp_path, checksum_offset=12):
    """Create a file with valid CRC32 checksum."""
    body = b"hello world test data"
    crc = zlib.crc32(body) & 0xFFFFFFFF

    data = bytearray(checksum_offset)
    data.extend(crc.to_bytes(4, "little"))
    data.extend(body)

    test_file = tmp_path / "input.bin"
    test_file.write_bytes(bytes(data))
    return test_file


def test_creates_mutated_file(tmp_path):
    """Command creates mutated output file with valid checksum."""
    test_file = _create_file_with_checksum(tmp_path)
    output_file = tmp_path / "output.bin"

    runner = CliRunner()
    result = runner.invoke(
        mint_cmd,
        ["--file", str(test_file), "--output", str(output_file), "--checksum-offset", "12"],
    )
    assert_cli_ok(result)
    assert output_file.exists()
    assert "Minted file created" in result.output
    assert "mutated_byte" in result.output
    assert "checksum" in result.output


def test_mutated_file_has_valid_checksum(tmp_path):
    """Mutated file has correct checksum for modified body."""
    test_file = _create_file_with_checksum(tmp_path)
    output_file = tmp_path / "output.bin"

    runner = CliRunner()
    runner.invoke(
        mint_cmd,
        ["--file", str(test_file), "--output", str(output_file), "--checksum-offset", "12"],
    )

    data = output_file.read_bytes()
    stored = int.from_bytes(data[12:16], "little")
    computed = zlib.crc32(data[16:]) & 0xFFFFFFFF

    assert stored == computed


def test_default_output_name(tmp_path):
    """Command uses default output name when not specified."""
    test_file = _create_file_with_checksum(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        mint_cmd,
        ["--file", str(test_file), "--checksum-offset", "12"],
    )
    assert_cli_ok(result)

    expected_output = tmp_path / "input.mint.bin"
    assert expected_output.exists()


def test_env_var_file(tmp_path, monkeypatch):
    """Command reads file from HEXSIR_FILE env var."""
    test_file = _create_file_with_checksum(tmp_path)
    output_file = tmp_path / "output.bin"

    monkeypatch.setenv("HEXSIR_FILE", str(test_file))

    runner = CliRunner()
    result = runner.invoke(
        mint_cmd,
        ["--output", str(output_file), "--checksum-offset", "12"],
    )
    assert_cli_ok(result)
    assert output_file.exists()


def test_missing_file():
    """Command errors when no file specified."""
    runner = CliRunner()
    result = runner.invoke(mint_cmd, ["--checksum-offset", "12"])
    assert result.exit_code != 0
    assert "HEXSIR_FILE" in result.output


def test_help():
    """Command --help shows description."""
    runner = CliRunner()
    result = runner.invoke(mint_cmd, ["--help"])
    assert_cli_ok(result)
