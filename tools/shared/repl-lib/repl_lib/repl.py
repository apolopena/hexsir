"""Generic async REPL engine with dispatch table pattern.

Provides a reusable interactive session loop for CLI tools. The tool declares
its state, builtins, and commands; the library handles the loop, prompt,
argument validation, help generation, and state management.

Builtins are REPL-level state setters, not commands. They parse one argument,
validate the type, and store it in the state dict. The library generates the
handler automatically from the declaration — no handler function needed.

    repl.builtin("session", arg="<id>", arg_type=int,
                  state_key="session_id", prompt_label="session",
                  help_text="Set active session ID")

Commands (insight, assessment, etc.) are tool-specific and go through the
dispatch function. Help text is auto-generated from Click command metadata
when commands are passed to the constructor.

Default builtins (exit, reset, help) are registered automatically.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from display_lib.output import error, info


class Repl:
    """Async REPL with builtin registry, state management, and dispatch.

    Args:
        name: Tool name shown in prompt (e.g. "adcli").
        dispatch: Async function that handles non-builtin commands.
            Signature: async (cmd_name: str, line: str, state: dict) -> None.
            Called when the user types a command that isn't a registered builtin.
            SystemExit exceptions are caught to prevent REPL crashes.
        initial_state: Starting state dict, copied on construction and on reset.
            Every state key used by builtins must be declared here.
        commands: Dict mapping command names to Click command objects.
            Used to auto-generate the Commands section in help output
            via Click's get_short_help_str().
        history_file: Path for persistent command history file.
            Defaults to ".<name>_history" in the current directory.
        help_footer: Optional text appended after the command list in help.
    """

    def __init__(
        self,
        name: str,
        dispatch: Callable[[str, str, dict], Awaitable[None]],
        initial_state: dict[str, Any] | None = None,
        commands: dict[str, Any] | None = None,
        history_file: str | None = None,
        help_footer: str | None = None,
    ) -> None:
        self.name = name
        self._dispatch = dispatch
        self._initial_state = dict(initial_state) if initial_state else {}
        self._commands = commands or {}
        self._history_file = history_file or f".{name}_history"
        self._help_footer = help_footer
        self._builtins: dict[str, _Builtin] = {}
        self.state: dict[str, Any] = {}

        # Prompt display — set at runtime via show_in_prompt(), cleared on reset.
        self._prompt_state_key: str | None = None
        self._prompt_state_label: str | None = None

        # Default builtins
        self._builtins["exit"] = _Builtin(
            handler=self._handle_exit,
            help_text="Exit interactive session",
        )
        self._builtins["reset"] = _Builtin(
            handler=self._handle_reset,
            help_text="Reset interactive session",
        )
        self._builtins["help"] = _Builtin(
            handler=self._handle_help,
            help_text="List commands and built-ins",
        )

    def builtin(
        self,
        name: str,
        arg: str,
        arg_type: type,
        state_key: str,
        help_text: str = "",
        usage: str | None = None,
        prompt_label: str | None = None,
        validator: Callable | None = None,
    ) -> None:
        """Register a state-setting builtin.

        Builtins are REPL-level state setters. The library generates the
        handler — parsing, validation, state updates, and prompt changes
        are automatic.

        Example:
            repl.builtin("session", arg="<id>", arg_type=int,
                          state_key="session_id", prompt_label="session",
                          help_text="Set active session ID")

        When the user types "session 10034":
        - Parses "10034" from the input
        - Validates it converts to int (shows usage error if not)
        - If validator is set, runs it; on error message, state is not updated
        - Sets state["session_id"] = 10034
        - Updates prompt to show "session:10034" (if prompt_label set)

        Args:
            name: Command name the user types.
            arg: Argument placeholder for help and error messages (e.g. "<id>").
            arg_type: Python type for validation (e.g. int, str).
            state_key: State dict key to set. Must exist in initial_state.
            help_text: Description shown in help output.
            usage: Usage string for help. Defaults to "name arg".
            prompt_label: If set, displays this state value in the prompt
                after setting it. Use to show "session" instead of "session_id".
            validator: Optional callback `(value) -> True | str`. Return True
                to accept the value; return an error message string to reject.
                May be sync or async (awaited if coroutine function).

        Raises:
            ValueError: If name conflicts with a default builtin, or if
                state_key is not in initial_state.
        """
        if name in ("exit", "reset", "help"):
            raise ValueError(f"Cannot override default builtin '{name}'")

        if state_key not in self._initial_state:
            raise ValueError(
                f"Builtin '{name}': state_key '{state_key}' not in initial_state"
            )

        resolved_usage = usage or f"{name} {arg}"
        handler = self._make_state_handler(
            name, resolved_usage, arg, arg_type, state_key, prompt_label, validator
        )
        self._builtins[name] = _Builtin(
            handler=handler,
            help_text=help_text,
            usage=resolved_usage,
        )

    def show_in_prompt(self, key: str, label: str | None = None) -> None:
        """Change which state value is displayed in the prompt.

        Only one value can be shown at a time. Calling this replaces any
        previously displayed value. Reset clears the prompt display.

        Prompt formats:
            No state set:        "toolname> "
            Value is None:       "toolname> "
            Label differs:       "toolname - label:value> "
            Label matches key:   "toolname:value> "

        Args:
            key: State dict key whose value to display.
            label: Human-readable label. Defaults to key name.
        """
        self._prompt_state_key = key
        self._prompt_state_label = label or key

    # --- Prompt ---

    def _build_prompt(self) -> str:
        """Build prompt string from current state."""
        if not self._prompt_state_key:
            return f"{self.name}> "

        value = self.state.get(self._prompt_state_key)
        if value is None:
            return f"{self.name}> "

        if self._prompt_state_label != self._prompt_state_key:
            return f"{self.name} - {self._prompt_state_label}:{value}> "
        return f"{self.name}:{value}> "

    # --- Help ---

    def _build_help(self) -> None:
        """Print help from registered builtins and Click commands.

        Sections:
            1. Built-ins (custom builtins + default builtins)
            2. Commands (auto-generated from Click command metadata)
            3. Optional footer text
        """
        lines = ["\nBuilt-ins:"]

        # Custom builtins first
        for name, builtin in self._builtins.items():
            if name in ("exit", "help", "reset"):
                continue
            usage = builtin.usage or name
            lines.append(f"  {usage:<28}{builtin.help_text}")

        # Default builtins
        lines.append(f"  {'reset':<28}Reset interactive session")
        lines.append(f"  {'help':<28}List commands and built-ins")
        lines.append(f"  {'exit':<28}Exit interactive session")

        # Commands from Click metadata
        if self._commands:
            lines.append("")
            lines.append("Commands:")
            for cmd_name, click_cmd in self._commands.items():
                help_text = click_cmd.get_short_help_str()
                lines.append(f"  {cmd_name:<28}{help_text}")

        if self._help_footer:
            lines.append("")
            lines.append(self._help_footer)

        lines.append("")
        print("\n".join(lines))

    # --- Generated handler ---

    def _make_state_handler(
        self,
        name: str,
        usage: str,
        arg: str,
        arg_type: type,
        state_key: str,
        prompt_label: str | None,
        validator: Callable | None,
    ) -> Callable:
        """Generate a handler from a declarative builtin registration.

        The generated handler:
            1. Splits the input line to extract the argument
            2. Validates the argument converts to arg_type
            3. Runs validator if provided; rejects with error message on failure
            4. Sets state[state_key] to the converted value
            5. Updates prompt display if prompt_label was provided
            6. Returns False (builtins never exit the REPL)

        On missing, invalid, or rejected argument, prints error to stderr.
        The returned handler is always async (validator may be async).
        """

        async def handler(line: str, state: dict, repl: Repl) -> bool:
            parts = line.split()
            if len(parts) < 2:
                error(f"Usage: {usage}")
                return False
            try:
                value = arg_type(parts[1])
            except (ValueError, TypeError):
                error(
                    f'{name}: "{parts[1]}" is not a valid {arg_type.__name__} for {arg}'
                )
                return False

            if validator is not None:
                try:
                    result = validator(value)
                    if inspect.iscoroutine(result):
                        result = await result
                except Exception as e:
                    error(f"{name}: validator raised {type(e).__name__}: {e}")
                    return False
                if result is not True:
                    msg = result if isinstance(result, str) else f"invalid {arg}"
                    error(f"{name}: {msg}")
                    return False

            state[state_key] = value
            if prompt_label:
                repl.show_in_prompt(state_key, prompt_label)
            info(f"Active {prompt_label or state_key}: {value}")
            return False

        return handler

    # --- Default handlers ---

    def _handle_exit(self, line: str, state: dict, repl: Repl) -> bool:
        """Exit the REPL."""
        return True

    def _handle_reset(self, line: str, state: dict, repl: Repl) -> bool:
        """Reset state to initial values and clear prompt display."""
        state.clear()
        state.update(self._initial_state)
        self._prompt_state_key = None
        self._prompt_state_label = None
        info("Reset interactive session")
        return False

    def _handle_help(self, line: str, state: dict, repl: Repl) -> bool:
        """Print auto-generated help."""
        self._build_help()
        return False

    # --- Main loop ---

    async def run(
        self,
        banner: Callable[[dict], None] | None = None,
        exit_msg: str | None = None,
    ) -> None:
        """Run the REPL loop.

        Reads input, matches against builtins, dispatches unknown commands.
        Handles KeyboardInterrupt (continues) and EOFError (exits).
        SystemExit from dispatch is caught to prevent REPL crashes.

        Args:
            banner: Optional callable(state) invoked before the loop.
            exit_msg: Optional message printed on exit. If None, exits silently.
        """
        self.state = dict(self._initial_state)
        prompt_session = PromptSession(
            history=FileHistory(self._history_file),
        )

        if banner:
            banner(self.state)

        while True:
            try:
                prompt = self._build_prompt()
                line = await prompt_session.prompt_async(prompt)
                line = line.strip()

                if not line:
                    continue

                cmd_name = line.split()[0]
                builtin = self._builtins.get(cmd_name)

                if builtin:
                    # Show help for built-ins without running the handler
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] in ("--help", "-h"):
                        usage = builtin.usage or cmd_name
                        print(f"\nBuilt-in:\n  {usage} — {builtin.help_text}\n")
                        continue
                    result = builtin.handler(line, self.state, self)
                    if inspect.iscoroutine(result):
                        result = await result
                    if result:
                        break
                else:
                    try:
                        await self._dispatch(cmd_name, line, self.state)
                    except SystemExit:
                        pass  # command error already printed, don't kill REPL

            except KeyboardInterrupt:
                continue
            except EOFError:
                break

        if exit_msg:
            info(exit_msg)


class _Builtin:
    """Internal: registered builtin command. Not used by tools directly."""

    __slots__ = ("handler", "help_text", "usage")

    def __init__(
        self,
        handler: Callable[[str, dict, Repl], bool],
        help_text: str = "",
        usage: str | None = None,
    ) -> None:
        self.handler = handler
        self.help_text = help_text
        self.usage = usage
