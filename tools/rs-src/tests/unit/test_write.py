"""Tests for write command."""

import struct
from unittest.mock import patch

from click.testing import CliRunner
from test_lib.cli import assert_cli_ok

from commands.write import write_cmd
from lib.errors import ShimRPCError, ShimUnreachable


def test_help():
    runner = CliRunner()
    result = runner.invoke(write_cmd, ["--help"])
    assert_cli_ok(result)
    assert "ADDR" in result.output
    assert "VALUE" in result.output
    assert "--as" in result.output


def test_quiet_int32_success():
    runner = CliRunner()
    captured = {}

    def fake_call(method, params=None, **kw):
        captured.update(params)
        return {"written": 4}

    with patch("commands.write.shim_client.call", side_effect=fake_call):
        result = runner.invoke(write_cmd, ["0x100", "5", "--as", "int32"])
    assert_cli_ok(result)
    assert captured["addr"] == 0x100
    assert captured["data_hex"] == "05000000"
    assert "<- 5" in result.output
    assert "int32" in result.output


def test_quiet_float32_success():
    runner = CliRunner()
    captured = {}

    def fake_call(method, params=None, **kw):
        captured.update(params)
        return {"written": 4}

    with patch("commands.write.shim_client.call", side_effect=fake_call):
        result = runner.invoke(write_cmd, ["0x100", "117.0", "--as", "float32"])
    assert_cli_ok(result)
    assert captured["data_hex"] == struct.pack("<f", 117.0).hex()
    assert "<- 117.0" in result.output


def test_quiet_hex_default():
    runner = CliRunner()
    captured = {}

    def fake_call(method, params=None, **kw):
        captured.update(params)
        return {"written": 4}

    with patch("commands.write.shim_client.call", side_effect=fake_call):
        result = runner.invoke(write_cmd, ["0x100", "deadbeef"])
    assert_cli_ok(result)
    assert captured["data_hex"] == "deadbeef"


def test_quiet_invalid_address():
    runner = CliRunner()
    result = runner.invoke(write_cmd, ["xyz", "5", "--as", "int32"])
    assert_cli_ok(result)
    assert "invalid address" in result.output.lower()


def test_quiet_encode_failure():
    runner = CliRunner()
    result = runner.invoke(write_cmd, ["0x100", "abc", "--as", "hex"])
    assert_cli_ok(result)
    assert "even-length" in result.output


def test_quiet_shim_unreachable():
    runner = CliRunner()
    with patch(
        "commands.write.shim_client.call",
        side_effect=ShimUnreachable("refused"),
    ):
        result = runner.invoke(write_cmd, ["0x100", "5", "--as", "int32"])
    assert_cli_ok(result)
    assert "refused" in result.output


def test_quiet_rpc_error():
    runner = CliRunner()
    with patch(
        "commands.write.shim_client.call",
        side_effect=ShimRPCError("not attached", kind="NotAttached"),
    ):
        result = runner.invoke(write_cmd, ["0x100", "5", "--as", "int32"])
    assert_cli_ok(result)
    assert "not attached" in result.output


def test_no_confirmation_prompt():
    """Writes happen immediately without any y/N prompt."""
    runner = CliRunner()
    with patch("commands.write.shim_client.call", return_value={"written": 4}):
        # Empty stdin — would hang or fail if a prompt were issued.
        result = runner.invoke(write_cmd, ["0x100", "5", "--as", "int32"], input="")
    assert_cli_ok(result)
    assert "Confirm" not in result.output
    assert "y/N" not in result.output


def test_verbose_emits_tree():
    runner = CliRunner()
    with (
        patch("commands.write.config.shim_host", return_value="1.2.3.4"),
        patch("commands.write.config.shim_port", return_value=8765),
        patch("commands.write.shim_client.call", return_value={"written": 4}),
    ):
        result = runner.invoke(write_cmd, ["0x100", "5", "--as", "int32", "--verbose"])
    assert_cli_ok(result)
    for needle in (
        "resolve shim host: 1.2.3.4:8765",
        "encode '5' as int32: 05000000",
        "write 0x100: 4 bytes",
    ):
        assert needle in result.output, f"missing {needle!r} in:\n{result.output}"


def test_verbose_write_failure_stops_tree():
    runner = CliRunner()
    with (
        patch("commands.write.config.shim_host", return_value="1.2.3.4"),
        patch("commands.write.config.shim_port", return_value=8765),
        patch(
            "commands.write.shim_client.call",
            side_effect=ShimUnreachable("refused"),
        ),
    ):
        result = runner.invoke(write_cmd, ["0x100", "5", "--as", "int32", "--verbose"])
    assert_cli_ok(result)
    assert "encode '5' as int32" in result.output
    assert "refused" in result.output
