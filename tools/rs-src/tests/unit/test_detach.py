"""Tests for detach command."""

from unittest.mock import patch

from click.testing import CliRunner

from commands.detach import detach_cmd
from lib.errors import ShimUnreachable


def test_help():
    runner = CliRunner()
    result = runner.invoke(detach_cmd, ["--help"])
    assert result.exit_code == 0


def test_success():
    runner = CliRunner()
    with patch("commands.detach.shim_client.call", return_value={"ok": True}):
        result = runner.invoke(detach_cmd, [])
    assert result.exit_code == 0
    assert "Detached" in result.output


def test_shim_unreachable_prints_error():
    runner = CliRunner()
    with patch(
        "commands.detach.shim_client.call",
        side_effect=ShimUnreachable("shim not reachable at 1.2.3.4:8765"),
    ):
        result = runner.invoke(detach_cmd, [])
    assert result.exit_code == 0
    assert "not reachable" in result.output
