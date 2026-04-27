"""Tests for read command."""

import struct
from unittest.mock import patch

from click.testing import CliRunner
from test_lib.cli import assert_cli_ok

from commands.read import read_cmd
from lib.errors import ShimUnreachable


def test_help():
    runner = CliRunner()
    result = runner.invoke(read_cmd, ["--help"])
    assert_cli_ok(result)
    assert "ADDR" in result.output
    assert "--as" in result.output


def test_quiet_int32_success():
    runner = CliRunner()
    with patch(
        "commands.read.shim_client.call",
        return_value="05000000",
    ):
        result = runner.invoke(read_cmd, ["0x27cdcfe8668", "--as", "int32"])
    assert_cli_ok(result)
    assert "0x27cdcfe8668" in result.output
    assert "int32" in result.output
    assert "= 5" in result.output


def test_quiet_float32_success():
    runner = CliRunner()
    with patch(
        "commands.read.shim_client.call",
        return_value=struct.pack("<f", 117.0).hex(),
    ):
        result = runner.invoke(read_cmd, ["0x100", "--as", "float32"])
    assert_cli_ok(result)
    assert "= 117.0" in result.output


def test_quiet_hex_default_length_4():
    runner = CliRunner()
    captured = {}

    def fake_call(method, params=None, **kw):
        captured.update(params)
        return "deadbeef"

    with patch("commands.read.shim_client.call", side_effect=fake_call):
        result = runner.invoke(read_cmd, ["0x100"])
    assert_cli_ok(result)
    assert captured["length"] == 4
    assert "= deadbeef" in result.output


def test_quiet_explicit_length_overrides_type_size():
    runner = CliRunner()
    captured = {}

    def fake_call(method, params=None, **kw):
        captured.update(params)
        return "deadbeefdeadbeef"

    with patch("commands.read.shim_client.call", side_effect=fake_call):
        result = runner.invoke(read_cmd, ["0x100", "--as", "hex", "--length", "8"])
    assert_cli_ok(result)
    assert captured["length"] == 8


def test_quiet_invalid_address():
    runner = CliRunner()
    result = runner.invoke(read_cmd, ["not-a-number"])
    assert_cli_ok(result)
    assert "invalid address" in result.output.lower()


def test_quiet_shim_unreachable_prints_friendly_error():
    runner = CliRunner()
    with patch(
        "commands.read.shim_client.call",
        side_effect=ShimUnreachable("shim not reachable at 1.2.3.4:8765 (refused)"),
    ):
        result = runner.invoke(read_cmd, ["0x100", "--as", "int32"])
    assert_cli_ok(result)
    assert "not reachable" in result.output


def test_quiet_decode_error_when_byte_count_mismatch():
    """Server returned 2 bytes but we asked for int32 (4)."""
    runner = CliRunner()
    with patch("commands.read.shim_client.call", return_value="0500"):
        result = runner.invoke(read_cmd, ["0x100", "--as", "int32", "--length", "2"])
    assert_cli_ok(result)
    assert "requires 4 bytes" in result.output


def test_verbose_emits_tree():
    runner = CliRunner()
    with (
        patch("commands.read.config.shim_host", return_value="1.2.3.4"),
        patch("commands.read.config.shim_port", return_value=8765),
        patch("commands.read.shim_client.call", return_value="05000000"),
    ):
        result = runner.invoke(
            read_cmd, ["0x27cdcfe8668", "--as", "int32", "--verbose"]
        )
    assert_cli_ok(result)
    for needle in (
        "resolve shim host: 1.2.3.4:8765",
        "read 0x27cdcfe8668",
        "decode as int32: 5",
    ):
        assert needle in result.output, f"missing {needle!r} in:\n{result.output}"


def test_verbose_read_failure_stops_tree():
    runner = CliRunner()
    with (
        patch("commands.read.config.shim_host", return_value="1.2.3.4"),
        patch("commands.read.config.shim_port", return_value=8765),
        patch(
            "commands.read.shim_client.call",
            side_effect=ShimUnreachable("refused"),
        ),
    ):
        result = runner.invoke(read_cmd, ["0x100", "--verbose"])
    assert_cli_ok(result)
    assert "resolve shim host" in result.output
    assert "refused" in result.output
    assert "decode as" not in result.output
