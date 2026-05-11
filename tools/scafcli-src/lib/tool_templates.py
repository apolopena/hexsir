"""Shared templates for tool scaffolding."""

import re

# Validation patterns
NAME_RE = re.compile(r"^[a-z]+$")
COMMAND_NAME_RE = re.compile(r"^[a-z]+(-[a-z]+)*$")

# Command file template
COMMAND_TEMPLATE = """\
\"\"\"{cmd_underscored} command.\"\"\"

import click

from display_lib.output import info, success


@click.command()
def {cmd_underscored}_cmd() -> None:
    \"\"\"TODO: describe this command.\"\"\"
    info("Running {cmd_underscored}...")
    success("Done")
"""

# Command test file template
COMMAND_TEST_TEMPLATE = """\
\"\"\"Tests for {cmd_underscored} command.\"\"\"

from click.testing import CliRunner
from commands.{cmd_underscored} import {cmd_underscored}_cmd
from test_lib.cli import assert_cli_ok


def test_runs():
    \"\"\"Command executes without error.\"\"\"
    runner = CliRunner()
    result = runner.invoke({cmd_underscored}_cmd, [])
    assert_cli_ok(result)


def test_help():
    \"\"\"Command --help shows description.\"\"\"
    runner = CliRunner()
    result = runner.invoke({cmd_underscored}_cmd, ["--help"])
    assert_cli_ok(result)
"""
