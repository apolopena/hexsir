"""Tests for find command."""

from unittest.mock import patch

from click.testing import CliRunner
from test_lib.cli import assert_cli_ok

from commands.find import find_cmd
from lib.errors import ShimUnreachable


def test_help():
    runner = CliRunner()
    result = runner.invoke(find_cmd, ["--help"])
    assert_cli_ok(result)
    assert "NEEDLE_HEX" in result.output
    assert "--alignment" in result.output
    assert "--out" in result.output


def test_quiet_summary_under_limit():
    runner = CliRunner()
    matches = [0x100, 0x200, 0x300]
    with patch("commands.find.shim_client.call", return_value=matches):
        result = runner.invoke(find_cmd, ["deadbeef"])
    assert_cli_ok(result)
    assert "3 match(es)" in result.output
    for addr in matches:
        assert f"0x{addr:x}" in result.output


def test_quiet_summary_truncated():
    runner = CliRunner()
    matches = [i * 0x10 for i in range(50)]
    with patch("commands.find.shim_client.call", return_value=matches):
        result = runner.invoke(find_cmd, ["deadbeef", "--limit", "5"])
    assert_cli_ok(result)
    assert "50 match(es)" in result.output
    assert "first 5" in result.output
    # First 5 addresses present
    assert "0x10" in result.output
    assert "0x40" in result.output
    # Truncation hint
    assert "45 more" in result.output


def test_quiet_all_disables_truncation():
    runner = CliRunner()
    matches = [i * 0x10 for i in range(50)]
    with patch("commands.find.shim_client.call", return_value=matches):
        result = runner.invoke(find_cmd, ["deadbeef", "--all"])
    assert_cli_ok(result)
    assert "50 match(es)" in result.output
    # All present, no truncation hint
    assert "0x1f0" in result.output  # last entry
    assert "more" not in result.output


def test_quiet_zero_matches():
    runner = CliRunner()
    with patch("commands.find.shim_client.call", return_value=[]):
        result = runner.invoke(find_cmd, ["deadbeef"])
    assert_cli_ok(result)
    assert "0 matches" in result.output


def test_quiet_out_file_dumps_full_list(tmp_path):
    runner = CliRunner()
    matches = [0x10, 0x20, 0x30]
    out = tmp_path / "matches.txt"
    with patch("commands.find.shim_client.call", return_value=matches):
        result = runner.invoke(find_cmd, ["deadbeef", "--out", str(out)])
    assert_cli_ok(result)
    assert "3 match(es)" in result.output
    assert str(out) in result.output
    written = out.read_text().strip().splitlines()
    assert written == ["0x10", "0x20", "0x30"]


def test_needle_with_0x_prefix():
    runner = CliRunner()
    captured = {}

    def fake_call(method, params=None, **kw):
        captured.update(params)
        return []

    with patch("commands.find.shim_client.call", side_effect=fake_call):
        result = runner.invoke(find_cmd, ["0xdeadbeef"])
    assert_cli_ok(result)
    assert captured["needle_hex"] == "deadbeef"


def test_needle_with_spaces():
    runner = CliRunner()
    captured = {}

    def fake_call(method, params=None, **kw):
        captured.update(params)
        return []

    with patch("commands.find.shim_client.call", side_effect=fake_call):
        result = runner.invoke(find_cmd, ["de ad be ef"])
    assert_cli_ok(result)
    assert captured["needle_hex"] == "deadbeef"


def test_alignment_passed_to_shim():
    runner = CliRunner()
    captured = {}

    def fake_call(method, params=None, **kw):
        captured.update(params)
        return []

    with patch("commands.find.shim_client.call", side_effect=fake_call):
        result = runner.invoke(find_cmd, ["deadbeef", "--alignment", "8"])
    assert_cli_ok(result)
    assert captured["alignment"] == 8


def test_invalid_needle_odd_length():
    runner = CliRunner()
    result = runner.invoke(find_cmd, ["abc"])
    assert_cli_ok(result)
    assert "even-length" in result.output


def test_invalid_alignment():
    runner = CliRunner()
    result = runner.invoke(find_cmd, ["deadbeef", "--alignment", "0"])
    assert_cli_ok(result)
    assert "alignment must be" in result.output


def test_quiet_shim_unreachable():
    runner = CliRunner()
    with patch(
        "commands.find.shim_client.call",
        side_effect=ShimUnreachable("refused"),
    ):
        result = runner.invoke(find_cmd, ["deadbeef"])
    assert_cli_ok(result)
    assert "refused" in result.output


def test_verbose_emits_tree():
    runner = CliRunner()
    with (
        patch("commands.find.config.shim_host", return_value="1.2.3.4"),
        patch("commands.find.config.shim_port", return_value=8765),
        patch("commands.find.shim_client.call", return_value=[0x100, 0x200]),
    ):
        result = runner.invoke(find_cmd, ["deadbeef", "--alignment", "4", "--verbose"])
    assert_cli_ok(result)
    for needle in (
        "resolve shim host: 1.2.3.4:8765",
        "needle: deadbeef (4 bytes), alignment=4",
        "scan: 2 match(es)",
    ):
        assert needle in result.output, f"missing {needle!r} in:\n{result.output}"
