#!/usr/bin/env python3
"""scafcli - Scaffold agentic layers for new repositories."""

import os
from importlib.metadata import version as pkg_version
from pathlib import Path

import click
import tomllib

# [auto] scaffold:imports — insertion point
from commands import (
    archive,
    command,
    inspect,
    repo,
    tool,
)

DIST_NAME = "scafcli-src"


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
    click.echo(f"scafcli {version}{suffix}")
    ctx.exit()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--version",
    is_flag=True,
    callback=_show_version,
    expose_value=False,
    is_eager=True,
    help="Show version",
)
def cli():
    """scafcli — Scaffold agentic layers for new repositories."""
    pass


# --- Top-level commands ---
cli.add_command(repo.repo_cmd, name="repo")


# --- tool group ---
@cli.group(name="tool")
def tool_():
    """Scaffold and manage CLI tools."""
    pass


tool_.add_command(tool.tool_cmd, name="new")


@tool_.group(name="add")
def tool_add():
    """Add components to an existing CLI tool."""
    pass


tool_add.add_command(command.command_cmd, name="command")


# --- archive group ---
@cli.group(name="archive")
def archive_():
    """Create tarball of scaffold output."""
    pass


archive_.add_command(archive.archive_cmd, name="repo")


# --- inspect group ---
@cli.group(name="inspect")
def inspect_():
    """Inspect repo scaffold templates."""
    pass


inspect_.add_command(inspect.templates_cmd, name="templates")


if __name__ == "__main__":
    cli(prog_name="scafcli")
