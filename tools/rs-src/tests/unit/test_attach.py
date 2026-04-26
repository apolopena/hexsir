"""Tests for attach command."""

from unittest.mock import patch

from click.testing import CliRunner

from commands.attach import attach_cmd
from lib.errors import ShimRPCError, ShimUnreachable


_SHIM_RESP = {
    "ok": True,
    "pid": 22768,
    "process_base": 0x00007ff60b9f0000,
    "process": "Ravenswatch.exe",
}


def test_help():
    runner = CliRunner()
    result = runner.invoke(attach_cmd, ["--help"])
    assert result.exit_code == 0
    assert "process" in result.output.lower()


def test_quiet_success():
    runner = CliRunner()
    with patch("commands.attach.shim_client.call", return_value=_SHIM_RESP):
        result = runner.invoke(attach_cmd, [])
    assert result.exit_code == 0
    assert "Attached to Ravenswatch.exe" in result.output
    assert "22768" in result.output


def test_quiet_unreachable_prints_friendly_error():
    runner = CliRunner()
    with patch(
        "commands.attach.shim_client.call",
        side_effect=ShimUnreachable("shim not reachable at 1.2.3.4:8765 (refused)"),
    ):
        result = runner.invoke(attach_cmd, [])
    assert result.exit_code == 0  # command itself succeeds; just prints error
    assert "not reachable" in result.output


def test_verbose_success_emits_tree():
    """Verbose mode emits a 4-step tree, all passing."""
    runner = CliRunner()
    with patch("commands.attach.config.shim_host", return_value="1.2.3.4"), \
         patch("commands.attach.config.shim_port", return_value=8765), \
         patch(
             "commands.attach.shim_client.call",
             side_effect=[
                 {"ok": True, "attached": False, "pid": None, "process_base": None},  # ping
                 _SHIM_RESP,  # attach
                 {"ok": True, "attached": True, "pid": 22768,
                  "process_base": 0x00007ff60b9f0000},  # verify
             ],
         ):
        result = runner.invoke(attach_cmd, ["--verbose"])
    assert result.exit_code == 0
    # The four step lines should appear in order.
    for needle in (
        "resolve shim host: 1.2.3.4:8765",
        "ping shim: idle",
        "attach Ravenswatch.exe",
        "verify state: attached",
    ):
        assert needle in result.output, f"missing {needle!r} in:\n{result.output}"


def test_verbose_attach_rpc_error_stops_tree():
    """Game not running → verbose tree shows ✗ at the attach step."""
    runner = CliRunner()
    with patch("commands.attach.config.shim_host", return_value="1.2.3.4"), \
         patch("commands.attach.config.shim_port", return_value=8765), \
         patch(
             "commands.attach.shim_client.call",
             side_effect=[
                 {"ok": True, "attached": False, "pid": None, "process_base": None},  # ping ok
                 ShimRPCError("game process not found", kind="ProcessNotFound"),  # attach fails
             ],
         ):
        result = runner.invoke(attach_cmd, ["--verbose"])
    assert result.exit_code == 0
    assert "ping shim: idle" in result.output
    assert "game process not found" in result.output
    # The verify step should NOT have run.
    assert "verify state" not in result.output


def test_verbose_ping_failure_stops_tree_early():
    runner = CliRunner()
    with patch("commands.attach.config.shim_host", return_value="1.2.3.4"), \
         patch("commands.attach.config.shim_port", return_value=8765), \
         patch(
             "commands.attach.shim_client.call",
             side_effect=ShimUnreachable("shim not reachable at 1.2.3.4:8765 (refused)"),
         ):
        result = runner.invoke(attach_cmd, ["--verbose"])
    assert result.exit_code == 0
    assert "resolve shim host" in result.output
    assert "ping shim" in result.output
    assert "not reachable" in result.output
    # No subsequent steps.
    assert "attach Ravenswatch.exe:" not in result.output
