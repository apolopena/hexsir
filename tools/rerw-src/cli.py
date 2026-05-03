"""rerw CLI."""

import asyncio
import os
import shlex
from importlib.metadata import version as pkg_version
from pathlib import Path
from types import SimpleNamespace

import click
import tomllib

from display_lib.output import error, header, info
from repl_lib import Repl

# [auto] scaffold:imports — insertion point
from commands import (
    cipher,
    decipher,
    experimental,
    game_assets,
    game_assets_inspect,
    mint_savefile,
    read_savefile,
    swap_savefile,
    write_savefile,
)

DIST_NAME = "rerw-src"

_help = "Ravenswatch reverse engineering tool."


def _read_version() -> str:
    pyproject = Path(__file__).resolve().parent / "pyproject.toml"
    if pyproject.exists():
        with pyproject.open("rb") as f:
            return tomllib.load(f)["project"]["version"]
    return pkg_version(DIST_NAME)


def _show_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    version = _read_version()
    suffix = " (dev source)" if os.getenv("TOOL_EXEC_MODE") == "dev-source" else ""
    click.echo(f"rerw {version}{suffix}")
    ctx.exit()


@click.group(help=_help, context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--version",
    is_flag=True,
    callback=_show_version,
    expose_value=False,
    is_eager=True,
    help="Show version",
)
def cli():
    pass


@click.group(name="swap")
def swap_():
    """Swap files in the Ravenswatch install (savefile, etc.)."""


# Subcommands of `swap`
swap_.add_command(swap_savefile.swap_savefile_cmd, name="savefile")


@click.group(name="read")
def read_():
    """Read field values from game artifacts (savefile, etc.)."""


# Subcommands of `read`
read_.add_command(read_savefile.read_savefile_cmd, name="savefile")


@click.group(name="write")
def write_():
    """Write field values into game artifacts (savefile, etc.)."""


# Subcommands of `write`
write_.add_command(write_savefile.write_savefile_cmd, name="savefile")


@click.group(name="mint")
def mint_():
    """Transactional mint: produce a clean starting save from a chapter-boss-kill proof."""


# Subcommands of `mint`
mint_.add_command(mint_savefile.mint_savefile_cmd, name="savefile")


@click.group(name="inspect")
def game_assets_inspect_() -> None:
    """Inspect bundled game-asset registries (heroes, talents, items)."""


# Subcommands of `game-assets inspect`
game_assets_inspect_.add_command(game_assets_inspect.heroes_cmd, name="heroes")
game_assets_inspect_.add_command(game_assets_inspect.talents_cmd, name="talents")
game_assets_inspect_.add_command(game_assets_inspect.items_cmd, name="items")
game_assets.game_assets_group.add_command(game_assets_inspect_, name="inspect")


# --- REPL ---
#
# Top-level commands shown in REPL `help` under "Commands:". The `swap`
# group is exposed via the `swap-savefile` built-in instead, so the REPL
# can offer a focused sub-mode for repeated invocations.
_CLICK_COMMANDS = {
    # [auto] scaffold:repl-commands — insertion point
    "cipher": cipher.cipher_cmd,
    "decipher": decipher.decipher_cmd,
    "game-assets": game_assets.game_assets_group,
}


def _invoke(click_cmd: click.Command, info_name: str, args: list[str]) -> None:
    """Run a Click command from the REPL without letting Click kill it."""
    if "--help" in args or "-h" in args:
        ctx = click.Context(click_cmd, info_name=info_name)
        click.echo(click_cmd.get_help(ctx))
        return
    try:
        ctx = click_cmd.make_context(info_name, args)
    except click.UsageError as e:
        error(str(e))
        return
    except SystemExit:
        return
    try:
        ctx.invoke(click_cmd, **ctx.params)
    except SystemExit:
        pass


def _split(line: str) -> list[str]:
    try:
        return shlex.split(line)
    except ValueError:
        return line.split()


async def _dispatch(cmd_name: str, line: str, state: dict) -> None:
    # In a sub-mode every line is treated as flags to that command.
    # Reject anything that doesn't start with `-` so users get a clear
    # usage hint instead of a confusing Click parser error.
    if state.get("context") == "swap-savefile":
        tokens = _split(line)
        if not tokens or not tokens[0].startswith("-"):
            error(
                "In swap-savefile mode, type flags only "
                "(e.g. `--source PATH --dest PATH`)."
            )
            info("Use `--help` to list flags, `exit` to leave the sub-mode.")
            return
        _invoke(swap_savefile.swap_savefile_cmd, "swap-savefile", tokens)
        return

    click_cmd = _CLICK_COMMANDS.get(cmd_name)
    if not click_cmd:
        error(f"Unknown command: {cmd_name}")
        info("Type 'help' for available commands")
        return

    _invoke(click_cmd, cmd_name, _split(line)[1:])


# --- Built-ins for sub-mode navigation ---
#
# repl-lib's public `builtin()` API requires an argument. These two are
# argless (back) and bivalent (swap-savefile takes either zero args to
# enter sub-mode, or flags to run inline). We register them by injecting
# into `_repl._builtins` directly with the same shape as repl-lib's
# internal `_Builtin` (handler / help_text / usage). Eventually this
# pattern can be folded back into repl-lib as a public method.


# TODO: REPL builtins for read-savefile / write-savefile
def _swap_savefile_builtin(line: str, state: dict, repl: Repl) -> bool:
    parts = _split(line)
    if len(parts) == 1:
        # Bare `swap-savefile` enters the sub-mode.
        state["context"] = "swap-savefile"
        repl.show_in_prompt("context")
        return False
    # `swap-savefile --source X --dest Y` — run once, stay at top level.
    _invoke(swap_savefile.swap_savefile_cmd, "swap-savefile", parts[1:])
    return False


def _exit_builtin(line: str, state: dict, repl: Repl) -> bool:
    """Leave the current sub-mode if in one; otherwise quit the REPL."""
    if state.get("context") is not None:
        state["context"] = None
        return False  # stay in REPL, prompt reverts to `rerw> `
    return True  # top level — break the loop


_repl = Repl(
    name="rerw",
    dispatch=_dispatch,
    initial_state={"context": None},
    commands=_CLICK_COMMANDS,
    history_file=".rerw_history",
    help_footer=(
        "Save file swap — sub-mode:\n"
        "  rerw> swap-savefile                          enter sub-mode\n"
        "  rerw:swap-savefile> --source X --dest Y      run with these flags\n"
        "  rerw:swap-savefile> --help                   list available flags\n"
        "  rerw:swap-savefile> reset                    leave sub-mode (clears state)\n"
        "\n"
        "Inline (no sub-mode):\n"
        "  rerw> swap-savefile --source X --dest Y      run once, stay at top"
    ),
)

# Inject custom built-ins (same shape as repl-lib's _Builtin).
_repl._builtins["swap-savefile"] = SimpleNamespace(
    handler=_swap_savefile_builtin,
    help_text="Replace the active save file. Bare to enter sub-mode; with flags to run inline.",
    usage="swap-savefile",
)
# Override the default `exit` so it leaves sub-modes instead of killing the REPL.
_repl._builtins["exit"] = SimpleNamespace(
    handler=_exit_builtin,
    help_text="Leave sub-mode if in one; otherwise exit interactive session.",
    usage="exit",
)


def _banner(state: dict) -> None:
    """Print REPL startup banner — built-ins and commands with descriptions.
    The examples footer is reserved for `help`.
    """
    header("rerw — interactive mode")

    custom = [
        (n, b) for n, b in _repl._builtins.items() if n not in ("exit", "help", "reset")
    ]
    defaults = [(n, _repl._builtins[n]) for n in ("reset", "help", "exit")]

    print("\nBuilt-ins:")
    for name, builtin in custom + defaults:
        usage = getattr(builtin, "usage", None) or name
        help_text = getattr(builtin, "help_text", "")
        print(f"  {usage:<28}{help_text}")

    if _CLICK_COMMANDS:
        print("\nCommands:")
        for cmd_name, click_cmd in _CLICK_COMMANDS.items():
            print(f"  {cmd_name:<28}{click_cmd.get_short_help_str()}")
    print()
    info("Type 'help' for sub-mode usage and examples.")


@click.command(name="interactive")
def interactive_cmd():
    """Start an interactive REPL session."""
    asyncio.run(_repl.run(banner=_banner, exit_msg="bye"))


# [auto] scaffold:commands — insertion point
cli.add_command(swap_, name="swap")
cli.add_command(read_, name="read")
cli.add_command(write_, name="write")
cli.add_command(mint_, name="mint")
cli.add_command(cipher.cipher_cmd, name="cipher")
cli.add_command(decipher.decipher_cmd, name="decipher")
cli.add_command(game_assets.game_assets_group, name="game-assets")
cli.add_command(experimental.experimental_grp, name="experimental")
cli.add_command(interactive_cmd, name="interactive")


if __name__ == "__main__":
    cli(prog_name="rerw")
