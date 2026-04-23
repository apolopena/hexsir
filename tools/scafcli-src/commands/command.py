"""scaffold command — add a command to an existing CLI tool."""

import click

from display_lib.output import error, info, success
from lib.paths import get_root_dir

from lib.tool_templates import COMMAND_NAME_RE, COMMAND_TEMPLATE, COMMAND_TEST_TEMPLATE

# Marker constants — must match what scaffold tool generates
MARKER_IMPORTS = "# [auto] scaffold:imports — insertion point"
MARKER_COMMANDS = "# [auto] scaffold:commands — insertion point"
MARKER_REPL_COMMANDS = "# [auto] scaffold:repl-commands — insertion point"


def _wire_cli_py(cli_py_path, cmd_underscored: str, cmd_hyphenated: str) -> bool:
    """Insert import and registration into cli.py using markers. Returns True if wired."""
    content = cli_py_path.read_text()

    if MARKER_IMPORTS not in content or MARKER_COMMANDS not in content:
        return False

    # Insert import: add to the parenthesized import block
    # Find the closing ) of the import block after the marker
    marker_pos = content.index(MARKER_IMPORTS)
    paren_close = content.index(")", marker_pos)
    insert_pos = content.rfind("\n", marker_pos, paren_close)
    new_import = f"    {cmd_underscored},"
    content = content[:insert_pos] + "\n" + new_import + content[insert_pos:]

    # Insert registration after marker
    marker_pos = content.index(MARKER_COMMANDS)
    end_of_line = content.index("\n", marker_pos)
    # Find the next non-empty line to insert before it at the same level
    registration = (
        f"cli.add_command({cmd_underscored}.{cmd_underscored}_cmd, "
        f'name="{cmd_hyphenated}")'
    )
    content = (
        content[: end_of_line + 1] + registration + "\n" + content[end_of_line + 1 :]
    )

    # REPL wiring (optional — only if markers present)
    if MARKER_REPL_COMMANDS in content:
        marker_pos = content.index(MARKER_REPL_COMMANDS)
        # Find the closing } of _CLICK_COMMANDS
        brace_close = content.index("}", marker_pos)
        insert_pos = content.rfind("\n", marker_pos, brace_close)
        entry = f'    "{cmd_hyphenated}": {cmd_underscored}.{cmd_underscored}_cmd,'
        content = content[:insert_pos] + "\n" + entry + content[insert_pos:]

    cli_py_path.write_text(content)
    return True


@click.command()
@click.argument("tool_name")
@click.argument("command_name")
def command_cmd(tool_name: str, command_name: str) -> None:
    """Add a command to an existing CLI tool.

    \b
    TOOL_NAME      Target tool (must exist as tools/<name>-src/)
    COMMAND_NAME   Command to add (lowercase, hyphens allowed)
    """
    # Validate command name
    if not COMMAND_NAME_RE.match(command_name):
        error(f"Invalid command name: {command_name}")
        info(
            "Command names must be lowercase letters and hyphens"
            " (no leading/trailing hyphens)"
        )
        raise SystemExit(1)

    repo_root = get_root_dir()
    tools_dir = repo_root / "tools"
    src_dir = tools_dir / f"{tool_name}-src"

    if not src_dir.exists():
        error(f"Tool not found: {src_dir}")
        raise SystemExit(1)

    cmd_underscored = command_name.replace("-", "_")

    # Check target files don't already exist
    cmd_file = src_dir / "commands" / f"{cmd_underscored}.py"
    test_file = src_dir / "tests" / "unit" / f"test_{cmd_underscored}.py"

    if cmd_file.exists():
        error(f"Command file already exists: {cmd_file}")
        raise SystemExit(1)
    if test_file.exists():
        error(f"Test file already exists: {test_file}")
        raise SystemExit(1)

    # Generate files
    cmd_file.parent.mkdir(parents=True, exist_ok=True)
    cmd_file.write_text(COMMAND_TEMPLATE.format(cmd_underscored=cmd_underscored))

    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(COMMAND_TEST_TEMPLATE.format(cmd_underscored=cmd_underscored))

    success("Created:")
    click.echo(f"  commands/{cmd_underscored}.py")
    click.echo(f"  tests/unit/test_{cmd_underscored}.py")

    # Try auto-wiring via markers
    cli_py = src_dir / "cli.py"
    if cli_py.exists() and _wire_cli_py(cli_py, cmd_underscored, command_name):
        click.echo()
        success("Wired into cli.py")
    else:
        click.echo()
        info("Add to cli.py:")
        click.echo(f"  from commands import {cmd_underscored}")
        click.echo(
            f"  cli.add_command({cmd_underscored}.{cmd_underscored}_cmd, "
            f'name="{command_name}")'
        )
