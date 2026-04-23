"""demotoolcli CLI."""

import os
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

import click
import tomllib
from backend_lib.env import check_env

# [auto] scaffold:imports — insertion point
from commands import (
    audit,
)

DIST_NAME = "demotoolcli-src"
REQUIRED_VARS = ["CLI_ROOT_DIR", "CLI_BACKEND_URL", "CLI_AGENTIC_BACKEND_URL"]

_help = "demotoolcli developer tool."
if os.getenv("TOOL_EXEC_MODE") != "dev-source":
    _help += f"\n\nEnvironment: {', '.join(REQUIRED_VARS)}"


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
    click.echo(f"demotoolcli {version}{suffix}")
    ctx.exit()


@click.group(help=_help, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--version", is_flag=True, callback=_show_version,
              expose_value=False, is_eager=True, help="Show version")
def cli():
    if "--help" not in sys.argv and "-h" not in sys.argv and len(sys.argv) > 1:
        check_env("demotoolcli", REQUIRED_VARS)


# [auto] scaffold:commands — insertion point
cli.add_command(audit.audit_cmd, name="audit")


import asyncio
import shlex

from display_lib.output import error
from repl_lib import Repl


# [auto] scaffold:repl-commands — insertion point
_CLICK_COMMANDS = {
    "audit": audit.audit_cmd,
}


async def _dispatch(cmd_name, line, state):
    click_cmd = _CLICK_COMMANDS.get(cmd_name)
    if not click_cmd:
        error(f"Unknown command: {cmd_name}")
        return
    try:
        args = shlex.split(line)[1:]
        ctx = click_cmd.make_context(cmd_name, args)
        ctx.invoke(click_cmd, **ctx.params)
    except click.UsageError as e:
        error(str(e))
    except SystemExit:
        pass


_repl = Repl(
    name="demotoolcli",
    dispatch=_dispatch,
    initial_state={},
    commands=_CLICK_COMMANDS,
    history_file=".demotoolcli_history",
)


@cli.command()
@click.pass_context
def interactive(ctx):
    """Start interactive session."""
    asyncio.run(_repl.run())


if __name__ == "__main__":
    cli(prog_name="demotoolcli")
