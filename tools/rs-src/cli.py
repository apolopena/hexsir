"""rs CLI."""

import asyncio
import os
import shlex
from importlib.metadata import version as pkg_version
from pathlib import Path

import click
import tomllib

from display_lib.output import error, info, success
from repl_lib import Repl

# [auto] scaffold:imports — insertion point
from commands import (
    attach,
    detach,
    status,
)
from commands.dev import dev_group

from lib import shim_client
from lib.errors import ShimError, ShimRPCError

DIST_NAME = "rs-src"

_help = "rs — Ravensmith trainer (live read/write of game stats)."


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
    click.echo(f"rs {version}{suffix}")
    ctx.exit()


@click.group(help=_help, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--version", is_flag=True, callback=_show_version,
              expose_value=False, is_eager=True, help="Show version")
def cli():
    pass


# [auto] scaffold:commands — insertion point
cli.add_command(attach.attach_cmd, name="attach")
cli.add_command(detach.detach_cmd, name="detach")
cli.add_command(status.status_cmd, name="status")
cli.add_command(dev_group, name="dev")


# --- REPL ---

# [auto] scaffold:repl-commands — insertion point
_CLICK_COMMANDS = {
    "attach": attach.attach_cmd,
    "detach": detach.detach_cmd,
    "status": status.status_cmd,
    "dev": dev_group,
}

_STATE_KEY_ATTACHED = "attached_process"


def _invoke_click(click_cmd, info_name, args, state):
    """Run a Click command and capture its return value (for state hooks)."""
    if "--help" in args or "-h" in args:
        ctx = click.Context(click_cmd, info_name=info_name)
        click.echo(click_cmd.get_help(ctx))
        return None
    try:
        ctx = click_cmd.make_context(info_name, args)
    except click.UsageError as e:
        error(str(e))
        return None
    except SystemExit:
        return None
    try:
        return ctx.invoke(click_cmd, **ctx.params)
    except SystemExit:
        return None


async def _dispatch(cmd_name, line, state):
    click_cmd = _CLICK_COMMANDS.get(cmd_name)
    if not click_cmd:
        error(f"Unknown command: {cmd_name}")
        return

    try:
        args = shlex.split(line)[1:]
    except ValueError:
        args = line.split()[1:]

    result = _invoke_click(click_cmd, cmd_name, args, state)

    # Post-invocation prompt-state hooks (keep cache in sync with shim).
    if cmd_name == "attach" and isinstance(result, dict) and result.get("ok"):
        state[_STATE_KEY_ATTACHED] = result.get("process")
    elif cmd_name == "detach" and isinstance(result, dict) and result.get("ok"):
        state[_STATE_KEY_ATTACHED] = None
    elif isinstance(result, dict) and "attached" in result and not result["attached"]:
        # status returned "not attached" — sync local cache.
        if state.get(_STATE_KEY_ATTACHED):
            info("(shim reports not attached — clearing local state)")
            state[_STATE_KEY_ATTACHED] = None


def _exit_with_detach(line, state, repl):
    """Override the default `exit` builtin to auto-detach first."""
    if state.get(_STATE_KEY_ATTACHED):
        try:
            shim_client.call("detach")
            success("Detached")
        except ShimRPCError:
            # already detached on shim side; fine.
            pass
        except ShimError as e:
            error(f"detach on exit failed: {e}")
        state[_STATE_KEY_ATTACHED] = None
    return True


def _build_repl() -> Repl:
    repl = Repl(
        name="rs",
        dispatch=_dispatch,
        initial_state={_STATE_KEY_ATTACHED: None},
        commands=_CLICK_COMMANDS,
        history_file=".rs_history",
    )
    repl.show_in_prompt(_STATE_KEY_ATTACHED)
    # Override default exit to auto-detach (option A).
    exit_builtin = repl._builtins["exit"]
    exit_builtin.handler = _exit_with_detach
    return repl


@cli.command()
@click.pass_context
def interactive(ctx):
    """Start interactive session."""
    asyncio.run(_build_repl().run())


if __name__ == "__main__":
    cli(prog_name="rs")
