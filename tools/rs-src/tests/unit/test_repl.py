"""Tests for REPL dispatch and exit hook in cli.py."""

import asyncio
from unittest.mock import MagicMock, patch


from cli import _STATE_KEY_ATTACHED, _dispatch, _exit_with_detach


def _run(coro):
    return (
        asyncio.get_event_loop().run_until_complete(coro)
        if not asyncio.iscoroutine(coro)
        else asyncio.run(coro)
    )


# ---- _dispatch ----


def test_unknown_command_prints_error():
    state = {_STATE_KEY_ATTACHED: None}
    with patch("cli.error") as mock_error:
        asyncio.run(_dispatch("nope", "nope", state))
    mock_error.assert_called_once()


def test_attach_success_updates_state():
    state = {_STATE_KEY_ATTACHED: None}
    fake_result = {
        "ok": True,
        "process": "Ravenswatch.exe",
        "pid": 22768,
        "process_base": 0x7FF60B9F0000,
    }
    with patch("cli._invoke_click", return_value=fake_result):
        asyncio.run(_dispatch("attach", "attach", state))
    assert state[_STATE_KEY_ATTACHED] == "Ravenswatch.exe"


def test_attach_failure_does_not_set_state():
    state = {_STATE_KEY_ATTACHED: None}
    with patch("cli._invoke_click", return_value=None):
        asyncio.run(_dispatch("attach", "attach", state))
    assert state[_STATE_KEY_ATTACHED] is None


def test_detach_clears_state():
    state = {_STATE_KEY_ATTACHED: "Ravenswatch.exe"}
    with patch("cli._invoke_click", return_value={"ok": True}):
        asyncio.run(_dispatch("detach", "detach", state))
    assert state[_STATE_KEY_ATTACHED] is None


def test_status_idle_clears_stale_local_state():
    """If shim says not attached but cache thinks attached, sync the cache."""
    state = {_STATE_KEY_ATTACHED: "Ravenswatch.exe"}
    fake_status = {"ok": True, "attached": False, "pid": None, "process_base": None}
    with (
        patch("cli._invoke_click", return_value=fake_status),
        patch("cli.info") as mock_info,
    ):
        asyncio.run(_dispatch("status", "status", state))
    assert state[_STATE_KEY_ATTACHED] is None
    mock_info.assert_called_once()


def test_status_attached_keeps_state():
    state = {_STATE_KEY_ATTACHED: "Ravenswatch.exe"}
    fake_status = {
        "ok": True,
        "attached": True,
        "pid": 22768,
        "process_base": 0x7FF60B9F0000,
    }
    with patch("cli._invoke_click", return_value=fake_status):
        asyncio.run(_dispatch("status", "status", state))
    assert state[_STATE_KEY_ATTACHED] == "Ravenswatch.exe"


# ---- _exit_with_detach ----


def test_exit_when_idle_does_not_call_detach():
    state = {_STATE_KEY_ATTACHED: None}
    with patch("cli.shim_client.call") as mock_call:
        result = _exit_with_detach("exit", state, MagicMock())
    assert result is True
    mock_call.assert_not_called()


def test_exit_when_attached_calls_detach():
    state = {_STATE_KEY_ATTACHED: "Ravenswatch.exe"}
    with patch("cli.shim_client.call", return_value={"ok": True}) as mock_call:
        result = _exit_with_detach("exit", state, MagicMock())
    assert result is True
    mock_call.assert_called_once_with("detach")
    assert state[_STATE_KEY_ATTACHED] is None


def test_exit_when_attached_tolerates_detach_failure():
    """Should not propagate ShimError exceptions from detach on exit."""
    from lib.errors import ShimUnreachable

    state = {_STATE_KEY_ATTACHED: "Ravenswatch.exe"}
    with patch(
        "cli.shim_client.call",
        side_effect=ShimUnreachable("shim down"),
    ):
        result = _exit_with_detach("exit", state, MagicMock())
    assert result is True
    assert state[_STATE_KEY_ATTACHED] is None
