"""Tests for watch command."""

import struct
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from test_lib.cli import assert_cli_ok

from commands.watch import watch_cmd
from lib.errors import ShimUnreachable


class _FakeSession:
    """In-memory stand-in for shim_client.Session.

    Returns hex strings from ``responses`` in order, one per ``call`` invocation.
    """

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def call(self, method, params=None):
        self.calls.append((method, params))
        if not self._responses:
            raise RuntimeError("FakeSession exhausted")
        return self._responses.pop(0)


def _patch_session(session):
    return patch("commands.watch.shim_client.Session", return_value=session)


def _patch_clock(times: list[float]):
    """Replace time.monotonic with a sequence; time.sleep with a no-op."""
    iterator = iter(times)
    return (
        patch("commands.watch.time.monotonic", side_effect=lambda: next(iterator)),
        patch("commands.watch.time.sleep", return_value=None),
    )


def test_help():
    runner = CliRunner()
    result = runner.invoke(watch_cmd, ["--help"])
    assert_cli_ok(result)
    assert "ADDR" in result.output
    assert "--interval" in result.output
    assert "--duration" in result.output
    assert "--all" in result.output


def test_quiet_baseline_then_unchanged_is_silent():
    """Default mode: only baseline + final summary print when nothing changes."""
    runner = CliRunner()
    session = _FakeSession(
        [
            "05000000",  # baseline
            "05000000",  # tick 1, unchanged
            "05000000",  # tick 2, unchanged
        ]
    )
    # monotonic sequence: t0_call, before-while-1, after-sleep-1, before-while-2, after-sleep-2, before-while-3
    times = [0.0, 0.0, 0.5, 0.5, 1.0, 1.0]
    cm_clock, cm_sleep = _patch_clock(times)
    with _patch_session(session), cm_clock, cm_sleep:
        result = runner.invoke(
            watch_cmd,
            [
                "0x100",
                "--as",
                "int32",
                "--interval",
                "0.5",
                "--duration",
                "1.0",
            ],
        )
    assert_cli_ok(result)
    assert "baseline" in result.output
    assert "0x100 = 5" in result.output
    # No change ticks should print.
    assert result.output.count("0x100 = 5") == 1  # only baseline
    assert "3 sample(s)" in result.output
    assert "0 change(s)" in result.output


def test_quiet_prints_on_change_only():
    runner = CliRunner()
    session = _FakeSession(
        [
            "05000000",  # baseline = 5
            "05000000",  # tick 1, unchanged
            "06000000",  # tick 2, changed → 6
            "06000000",  # tick 3, unchanged at 6
        ]
    )
    times = [0.0, 0.0, 0.5, 0.5, 1.0, 1.0, 1.5, 1.5]
    cm_clock, cm_sleep = _patch_clock(times)
    with _patch_session(session), cm_clock, cm_sleep:
        result = runner.invoke(
            watch_cmd,
            [
                "0x100",
                "--as",
                "int32",
                "--interval",
                "0.5",
                "--duration",
                "1.5",
            ],
        )
    assert_cli_ok(result)
    assert "0x100 = 5" in result.output  # baseline
    assert "0x100 = 6" in result.output  # change
    # Marker on changed line
    assert " *" in result.output
    assert "1 change(s)" in result.output


def test_all_prints_every_tick():
    runner = CliRunner()
    session = _FakeSession(
        [
            "05000000",  # baseline
            "05000000",  # tick 1
            "05000000",  # tick 2
        ]
    )
    times = [0.0, 0.0, 0.5, 0.5, 1.0, 1.0]
    cm_clock, cm_sleep = _patch_clock(times)
    with _patch_session(session), cm_clock, cm_sleep:
        result = runner.invoke(
            watch_cmd,
            [
                "0x100",
                "--as",
                "int32",
                "--interval",
                "0.5",
                "--duration",
                "1.0",
                "--all",
            ],
        )
    assert_cli_ok(result)
    # Three rows total (baseline + 2 ticks), all showing value 5.
    assert result.output.count("0x100 = 5") == 3


def test_invalid_address():
    runner = CliRunner()
    result = runner.invoke(watch_cmd, ["xyz"])
    assert_cli_ok(result)
    assert "invalid address" in result.output.lower()


def test_invalid_interval():
    runner = CliRunner()
    result = runner.invoke(watch_cmd, ["0x100", "--interval", "0"])
    assert_cli_ok(result)
    assert "interval must be" in result.output


def test_invalid_duration():
    runner = CliRunner()
    result = runner.invoke(watch_cmd, ["0x100", "--duration", "0"])
    assert_cli_ok(result)
    assert "duration must be" in result.output


def test_session_unreachable():
    runner = CliRunner()
    session = MagicMock()
    session.__enter__.side_effect = ShimUnreachable("refused")
    with patch("commands.watch.shim_client.Session", return_value=session):
        result = runner.invoke(
            watch_cmd, ["0x100", "--duration", "0.5", "--interval", "0.1"]
        )
    assert_cli_ok(result)
    assert "refused" in result.output


def test_uses_session_not_per_call_call():
    """Verify the persistent Session is used (not shim_client.call)."""
    runner = CliRunner()
    session = _FakeSession(["05000000", "05000000"])
    times = [0.0, 0.0, 0.5, 0.5]
    cm_clock, cm_sleep = _patch_clock(times)
    with _patch_session(session), cm_clock, cm_sleep:
        result = runner.invoke(
            watch_cmd,
            [
                "0x100",
                "--as",
                "int32",
                "--interval",
                "0.5",
                "--duration",
                "0.5",
            ],
        )
    assert_cli_ok(result)
    # Two RPCs: baseline + 1 tick — both routed through the Session.
    assert len(session.calls) == 2
    assert all(method == "read" for method, _ in session.calls)


def test_float32_progression():
    """Float values format cleanly across ticks."""
    runner = CliRunner()
    session = _FakeSession(
        [
            struct.pack("<f", 117.0).hex(),
            struct.pack("<f", 110.0).hex(),
        ]
    )
    times = [0.0, 0.0, 0.5, 0.5]
    cm_clock, cm_sleep = _patch_clock(times)
    with _patch_session(session), cm_clock, cm_sleep:
        result = runner.invoke(
            watch_cmd,
            [
                "0x100",
                "--as",
                "float32",
                "--interval",
                "0.5",
                "--duration",
                "0.5",
            ],
        )
    assert_cli_ok(result)
    assert "117.0" in result.output
    assert "110.0" in result.output


def test_verbose_emits_tree():
    runner = CliRunner()
    session = _FakeSession(["05000000"])
    # t0=0.0 then immediately past duration so the loop exits after baseline.
    times = [0.0, 100.0]
    cm_clock, cm_sleep = _patch_clock(times)
    with (
        patch("commands.watch.config.shim_host", return_value="1.2.3.4"),
        patch("commands.watch.config.shim_port", return_value=8765),
        _patch_session(session),
        cm_clock,
        cm_sleep,
    ):
        result = runner.invoke(
            watch_cmd,
            [
                "0x100",
                "--as",
                "int32",
                "--interval",
                "0.1",
                "--duration",
                "10",
                "--verbose",
            ],
        )
    assert_cli_ok(result)
    for needle in (
        "resolve shim host: 1.2.3.4:8765",
        "target: 0x100 (4 bytes, int32)",
    ):
        assert needle in result.output, f"missing {needle!r} in:\n{result.output}"
