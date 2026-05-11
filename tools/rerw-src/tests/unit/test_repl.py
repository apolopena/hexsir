"""Tests for REPL dispatch and custom built-ins."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from cli import _dispatch, _exit_builtin, _swap_savefile_builtin
from commands.swap_savefile import SAVE_FILENAME


# --- swap-savefile built-in ---


def test_swap_savefile_builtin_bare_enters_submode():
    """`swap-savefile` with no args sets the sub-mode context."""
    state = {"context": None}
    repl = MagicMock()
    result = _swap_savefile_builtin("swap-savefile", state, repl)
    assert result is False
    assert state["context"] == "swap-savefile"
    repl.show_in_prompt.assert_called_once_with("context")


def test_swap_savefile_builtin_with_flags_runs_inline(tmp_path: Path, monkeypatch):
    """`swap-savefile --source ... --dest ...` runs without entering sub-mode."""
    src = tmp_path / "src.ob"
    src.write_bytes(b"inline")
    dest = tmp_path / "save"
    dest.mkdir()
    monkeypatch.delenv("RERW_SAVEGAME_DIR", raising=False)

    state = {"context": None}
    repl = MagicMock()
    line = f"swap-savefile --source {src} --dest {dest}"
    result = _swap_savefile_builtin(line, state, repl)

    assert result is False
    assert state["context"] is None  # did not enter sub-mode
    repl.show_in_prompt.assert_not_called()
    assert (dest / SAVE_FILENAME).read_bytes() == b"inline"


# --- exit built-in ---


def test_exit_builtin_in_submode_clears_context():
    """`exit` while in a sub-mode clears the context and stays in REPL."""
    state = {"context": "swap-savefile"}
    result = _exit_builtin("exit", state, MagicMock())
    assert result is False
    assert state["context"] is None


def test_exit_builtin_at_top_level_signals_exit():
    """`exit` at top level returns True (REPL loop breaks)."""
    state = {"context": None}
    result = _exit_builtin("exit", state, MagicMock())
    assert result is True


# --- dispatch ---


def test_dispatch_unknown_top_level_command(capsys):
    """Unknown command at top level prints an error, doesn't raise."""
    state = {"context": None}
    asyncio.run(_dispatch("nope", "nope arg", state))
    out = capsys.readouterr()
    combined = out.out + out.err
    assert "Unknown command" in combined


def test_dispatch_in_submode_routes_to_swap_savefile(tmp_path: Path, monkeypatch):
    """In sub-mode, any line is passed as flags to swap_savefile_cmd."""
    src = tmp_path / "src.ob"
    src.write_bytes(b"submode")
    dest = tmp_path / "save"
    dest.mkdir()
    monkeypatch.setenv("RERW_SAVEGAME_DIR", str(dest))

    state = {"context": "swap-savefile"}
    asyncio.run(_dispatch("--source", f"--source {src}", state))
    assert (dest / SAVE_FILENAME).read_bytes() == b"submode"


def test_dispatch_in_submode_rejects_non_flag_input(capsys, monkeypatch):
    """In sub-mode, input that doesn't start with `-` shows a usage hint."""
    captured = []

    def fake_invoke(*args, **kwargs):
        captured.append((args, kwargs))

    monkeypatch.setattr("cli._invoke", fake_invoke)

    state = {"context": "swap-savefile"}
    asyncio.run(_dispatch("swap", "swap --from", state))

    out = capsys.readouterr()
    combined = out.out + out.err
    assert "flags only" in combined.lower()
    assert captured == []  # swap_savefile_cmd was NOT invoked


def test_dispatch_in_submode_routes_flag_input(monkeypatch):
    """In sub-mode, lines that start with `-` are routed to swap_savefile."""
    captured = []

    def fake_invoke(click_cmd, info_name, args):
        captured.append((info_name, list(args)))

    monkeypatch.setattr("cli._invoke", fake_invoke)

    state = {"context": "swap-savefile"}
    asyncio.run(_dispatch("--help", "--help", state))

    assert len(captured) == 1
    info_name, args = captured[0]
    assert info_name == "swap-savefile"
    assert args == ["--help"]


def test_dispatch_top_level_invokes_known_command(monkeypatch):
    """Known top-level command is dispatched via _invoke with its args."""
    captured = []

    def fake_invoke(click_cmd, info_name, args):
        captured.append((info_name, list(args)))

    monkeypatch.setattr("cli._invoke", fake_invoke)

    state = {"context": None}
    asyncio.run(_dispatch("cipher", "cipher abc", state))

    assert len(captured) == 1
    info_name, args = captured[0]
    assert info_name == "cipher"
    assert args == ["abc"]
