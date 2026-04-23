"""Unit tests for repl_lib."""

import asyncio

import pytest

from repl_lib import Repl


async def _noop_dispatch(cmd_name, line, state):
    """No-op dispatch for testing."""
    pass


def _make_click_cmd(help_text="A test command."):
    """Create a minimal Click-like command object for testing."""

    class FakeCmd:
        def get_short_help_str(self, limit=150):
            return help_text

    return FakeCmd()


class TestReplConstruction:
    """Tests for Repl initialization and validation."""

    def test_creates_with_minimal_args(self):
        """Repl can be created with just name and dispatch."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        assert repl.name == "test"

    def test_creates_with_initial_state(self):
        """Repl copies initial state."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        assert repl._initial_state == {"session_id": None}

    def test_initial_state_is_copied(self):
        """Mutating initial_state dict after construction has no effect."""
        original = {"session_id": None}
        repl = Repl(name="test", dispatch=_noop_dispatch, initial_state=original)
        original["session_id"] = 999
        assert repl._initial_state["session_id"] is None

    def test_default_history_file(self):
        """Default history file derives from tool name."""
        repl = Repl(name="mytool", dispatch=_noop_dispatch)
        assert repl._history_file == ".mytool_history"

    def test_custom_history_file(self):
        """Custom history file overrides default."""
        repl = Repl(
            name="mytool", dispatch=_noop_dispatch, history_file=".custom_history"
        )
        assert repl._history_file == ".custom_history"

    def test_default_builtins_registered(self):
        """exit, reset, help are registered by default."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        assert "exit" in repl._builtins
        assert "reset" in repl._builtins
        assert "help" in repl._builtins

    def test_prompt_starts_plain(self):
        """Prompt has no state display until show_in_prompt is called."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        repl.state = {}
        assert repl._build_prompt() == "test> "

    def test_stores_commands(self):
        """Commands dict is stored for help generation."""
        cmds = {"foo": _make_click_cmd()}
        repl = Repl(name="test", dispatch=_noop_dispatch, commands=cmds)
        assert repl._commands == cmds


class TestPromptBuilding:
    """Tests for prompt string generation."""

    def test_plain_prompt_no_state(self):
        """No show_in_prompt call produces plain prompt."""
        repl = Repl(name="mytool", dispatch=_noop_dispatch)
        repl.state = {}
        assert repl._build_prompt() == "mytool> "

    def test_state_value_none_shows_plain(self):
        """State key with None value produces plain prompt."""
        repl = Repl(
            name="mytool",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.state = {"session_id": None}
        repl.show_in_prompt("session_id", "session")
        assert repl._build_prompt() == "mytool> "

    def test_state_value_with_label(self):
        """State key with different label shows labeled format."""
        repl = Repl(
            name="mytool",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.state = {"session_id": 10034}
        repl.show_in_prompt("session_id", "session")
        assert repl._build_prompt() == "mytool - session:10034> "

    def test_state_value_label_matches_key(self):
        """When label matches key, uses compact format."""
        repl = Repl(
            name="mytool",
            dispatch=_noop_dispatch,
            initial_state={"env": None},
        )
        repl.state = {"env": "staging"}
        repl.show_in_prompt("env")
        assert repl._build_prompt() == "mytool:staging> "

    def test_show_in_prompt_switches_display(self):
        """Calling show_in_prompt switches what's displayed."""
        repl = Repl(
            name="mytool",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None, "env": None},
        )
        repl.state = {"session_id": 42, "env": "prod"}
        repl.show_in_prompt("session_id", "session")
        assert "session:42" in repl._build_prompt()
        repl.show_in_prompt("env")
        assert "prod" in repl._build_prompt()


class TestDeclarativeBuiltins:
    """Tests for state-setting builtin registration."""

    def test_registers_builtin(self):
        """Builtin is added to registry."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            help_text="Set session",
        )
        assert "session" in repl._builtins

    def test_handler_sets_state(self):
        """Handler parses argument and sets state."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            help_text="Set session",
        )
        repl.state = {"session_id": None}
        handler = repl._builtins["session"].handler
        result = asyncio.run(handler("session 42", repl.state, repl))
        assert repl.state["session_id"] == 42
        assert result is False

    def test_handler_validates_type(self, capsys):
        """Handler rejects invalid argument type."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            help_text="Set session",
        )
        repl.state = {"session_id": None}
        handler = repl._builtins["session"].handler
        asyncio.run(handler("session abc", repl.state, repl))
        captured = capsys.readouterr()
        assert 'session: "abc" is not a valid int for <id>' in captured.err
        assert repl.state["session_id"] is None

    def test_handler_missing_arg(self, capsys):
        """Handler shows usage when argument is missing."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            help_text="Set session",
        )
        repl.state = {"session_id": None}
        handler = repl._builtins["session"].handler
        asyncio.run(handler("session", repl.state, repl))
        captured = capsys.readouterr()
        assert "Usage: session <id>" in captured.err

    def test_handler_updates_prompt(self):
        """Handler with prompt_label updates prompt display."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            prompt_label="session",
            help_text="Set session",
        )
        repl.state = {"session_id": None}
        handler = repl._builtins["session"].handler
        asyncio.run(handler("session 99", repl.state, repl))
        assert repl._prompt_state_key == "session_id"
        assert repl._prompt_state_label == "session"

    def test_handler_no_prompt_label(self):
        """Handler without prompt_label leaves prompt unchanged."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"mode": None},
        )
        repl.builtin(
            "mode",
            arg="<name>",
            arg_type=str,
            state_key="mode",
            help_text="Set mode",
        )
        repl.state = {"mode": None}
        handler = repl._builtins["mode"].handler
        asyncio.run(handler("mode debug", repl.state, repl))
        assert repl.state["mode"] == "debug"
        assert repl._prompt_state_key is None

    def test_auto_generates_usage(self):
        """Usage string is auto-generated from name + arg."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            help_text="Set session",
        )
        assert repl._builtins["session"].usage == "session <id>"

    def test_string_arg_type(self):
        """String arg_type stores value without conversion issues."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"env": None},
        )
        repl.builtin(
            "env",
            arg="<name>",
            arg_type=str,
            state_key="env",
            help_text="Set environment",
        )
        repl.state = {"env": None}
        handler = repl._builtins["env"].handler
        asyncio.run(handler("env production", repl.state, repl))
        assert repl.state["env"] == "production"


class TestBuiltinValidator:
    """Tests for the optional validator callback on builtins."""

    def _make_repl(self, validator):
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            help_text="Set session",
            validator=validator,
        )
        repl.state = {"session_id": None}
        return repl

    def test_sync_validator_returns_true_sets_state(self):
        """Sync validator returning True allows state update."""
        repl = self._make_repl(lambda v: True)
        handler = repl._builtins["session"].handler
        asyncio.run(handler("session 42", repl.state, repl))
        assert repl.state["session_id"] == 42

    def test_sync_validator_returns_error_blocks_state(self, capsys):
        """Sync validator returning a string blocks state update."""
        repl = self._make_repl(lambda v: "session 42 not found in DB")
        handler = repl._builtins["session"].handler
        asyncio.run(handler("session 42", repl.state, repl))
        captured = capsys.readouterr()
        assert "session 42 not found in DB" in captured.err
        assert repl.state["session_id"] is None

    def test_async_validator_returns_true_sets_state(self):
        """Async validator returning True allows state update."""

        async def validator(v):
            return True

        repl = self._make_repl(validator)
        handler = repl._builtins["session"].handler
        asyncio.run(handler("session 42", repl.state, repl))
        assert repl.state["session_id"] == 42

    def test_async_validator_returns_error_blocks_state(self, capsys):
        """Async validator returning a string blocks state update."""

        async def validator(v):
            return "no such session"

        repl = self._make_repl(validator)
        handler = repl._builtins["session"].handler
        asyncio.run(handler("session 42", repl.state, repl))
        captured = capsys.readouterr()
        assert "no such session" in captured.err
        assert repl.state["session_id"] is None

    def test_validator_exception_handled(self, capsys):
        """Validator raising an exception prints error and blocks state."""

        def validator(v):
            raise RuntimeError("DB connection failed")

        repl = self._make_repl(validator)
        handler = repl._builtins["session"].handler
        asyncio.run(handler("session 42", repl.state, repl))
        captured = capsys.readouterr()
        assert "RuntimeError" in captured.err
        assert "DB connection failed" in captured.err
        assert repl.state["session_id"] is None

    def test_no_validator_works_as_before(self):
        """Builtin without validator works as before (backward compat)."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            help_text="Set session",
        )
        repl.state = {"session_id": None}
        handler = repl._builtins["session"].handler
        asyncio.run(handler("session 42", repl.state, repl))
        assert repl.state["session_id"] == 42


class TestBuiltinValidation:
    """Tests for builtin registration validation errors."""

    def test_rejects_missing_state_key(self):
        """state_key must exist in initial_state."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        with pytest.raises(ValueError, match="not in initial_state"):
            repl.builtin(
                "env",
                arg="<name>",
                arg_type=str,
                state_key="environment",
                help_text="Set env",
            )

    def test_rejects_override_exit(self):
        """Cannot override default builtin 'exit'."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"x": None},
        )
        with pytest.raises(ValueError, match="Cannot override"):
            repl.builtin("exit", arg="<x>", arg_type=str, state_key="x")

    def test_rejects_override_reset(self):
        """Cannot override default builtin 'reset'."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"x": None},
        )
        with pytest.raises(ValueError, match="Cannot override"):
            repl.builtin("reset", arg="<x>", arg_type=str, state_key="x")

    def test_rejects_override_help(self):
        """Cannot override default builtin 'help'."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"x": None},
        )
        with pytest.raises(ValueError, match="Cannot override"):
            repl.builtin("help", arg="<x>", arg_type=str, state_key="x")


class TestDefaultHandlers:
    """Tests for default builtin behavior (exit, reset, help)."""

    def test_exit_returns_true(self):
        """Exit handler signals loop termination."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        result = repl._handle_exit("exit", {}, repl)
        assert result is True

    def test_reset_restores_initial_state(self):
        """Reset restores state to initial values."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None, "mode": "default"},
        )
        state = {"session_id": 42, "mode": "debug"}
        repl._handle_reset("reset", state, repl)
        assert state == {"session_id": None, "mode": "default"}

    def test_reset_clears_prompt_display(self):
        """Reset clears any prompt state display."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.show_in_prompt("session_id", "session")
        repl._handle_reset("reset", repl.state, repl)
        assert repl._prompt_state_key is None
        assert repl._prompt_state_label is None

    def test_reset_returns_false(self):
        """Reset does not signal exit."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        result = repl._handle_reset("reset", {}, repl)
        assert result is False

    def test_help_returns_false(self):
        """Help does not signal exit."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        result = repl._handle_help("help", {}, repl)
        assert result is False

    def test_help_includes_default_builtins(self, capsys):
        """Help lists exit, reset, help."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        repl._handle_help("help", {}, repl)
        captured = capsys.readouterr()
        assert "exit" in captured.out
        assert "reset" in captured.out
        assert "help" in captured.out

    def test_help_includes_registered_builtins(self, capsys):
        """Help lists registered builtins with usage."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            help_text="Set session ID",
        )
        repl._handle_help("help", {}, repl)
        captured = capsys.readouterr()
        assert "session <id>" in captured.out
        assert "Set session ID" in captured.out

    def test_help_includes_click_commands(self, capsys):
        """Help lists commands from Click metadata."""
        cmds = {"insight": _make_click_cmd("Test insight generation.")}
        repl = Repl(name="test", dispatch=_noop_dispatch, commands=cmds)
        repl._handle_help("help", {}, repl)
        captured = capsys.readouterr()
        assert "insight" in captured.out
        assert "Test insight generation." in captured.out

    def test_help_includes_footer(self, capsys):
        """Help includes footer text when provided."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            help_footer="Use --help for details.",
        )
        repl._handle_help("help", {}, repl)
        captured = capsys.readouterr()
        assert "Use --help for details." in captured.out


class TestHelpGeneration:
    """Tests for help text structure."""

    def test_builtins_section_header(self, capsys):
        """Help starts with Built-ins header."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        repl._build_help()
        captured = capsys.readouterr()
        assert "Built-ins:" in captured.out

    def test_commands_section_header(self, capsys):
        """Help includes Commands header when commands provided."""
        cmds = {"foo": _make_click_cmd()}
        repl = Repl(name="test", dispatch=_noop_dispatch, commands=cmds)
        repl._build_help()
        captured = capsys.readouterr()
        assert "Commands:" in captured.out

    def test_no_commands_section_without_commands(self, capsys):
        """No Commands header when no commands provided."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        repl._build_help()
        captured = capsys.readouterr()
        assert "Commands:" not in captured.out

    def test_builtins_before_commands(self, capsys):
        """Built-ins section appears before Commands section."""
        cmds = {"foo": _make_click_cmd()}
        repl = Repl(name="test", dispatch=_noop_dispatch, commands=cmds)
        repl._build_help()
        captured = capsys.readouterr()
        assert captured.out.index("Built-ins:") < captured.out.index("Commands:")

    def test_custom_builtin_before_defaults(self, capsys):
        """Custom builtins appear before default builtins."""
        repl = Repl(
            name="test",
            dispatch=_noop_dispatch,
            initial_state={"session_id": None},
        )
        repl.builtin(
            "session",
            arg="<id>",
            arg_type=int,
            state_key="session_id",
            help_text="Set session ID",
        )
        repl._build_help()
        captured = capsys.readouterr()
        assert captured.out.index("session <id>") < captured.out.index("reset")

    def test_help_describes_itself_accurately(self, capsys):
        """Help builtin describes its function without self-reference."""
        repl = Repl(name="test", dispatch=_noop_dispatch)
        repl._build_help()
        captured = capsys.readouterr()
        assert "List commands and built-ins" in captured.out
        assert "Show this help" not in captured.out
