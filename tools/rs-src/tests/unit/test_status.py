"""Tests for status command."""

from unittest.mock import patch

from click.testing import CliRunner

from commands.status import status_cmd
from lib.errors import ShimUnreachable


def test_help():
    runner = CliRunner()
    result = runner.invoke(status_cmd, ["--help"])
    assert result.exit_code == 0


def test_attached_state():
    runner = CliRunner()
    with patch(
        "commands.status.shim_client.call",
        return_value={
            "ok": True,
            "attached": True,
            "pid": 22768,
            "process_base": 0x00007FF60B9F0000,
        },
    ):
        result = runner.invoke(status_cmd, [])
    assert result.exit_code == 0
    assert "attached" in result.output.lower()
    assert "22768" in result.output


def test_idle_state():
    runner = CliRunner()
    with patch(
        "commands.status.shim_client.call",
        return_value={
            "ok": True,
            "attached": False,
            "pid": None,
            "process_base": None,
        },
    ):
        result = runner.invoke(status_cmd, [])
    assert result.exit_code == 0
    assert "idle" in result.output.lower()


def test_shim_unreachable_prints_error():
    runner = CliRunner()
    with patch(
        "commands.status.shim_client.call",
        side_effect=ShimUnreachable("shim not reachable at 1.2.3.4:8765"),
    ):
        result = runner.invoke(status_cmd, [])
    assert result.exit_code == 0
    assert "not reachable" in result.output
