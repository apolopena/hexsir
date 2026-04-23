"""scaffold tool command — generate a new CLI tool skeleton."""

import stat
import subprocess
from datetime import date

import click

from display_lib.output import error, info, success
from lib.paths import get_root_dir
from lib.tool_templates import (
    COMMAND_NAME_RE,
    COMMAND_TEMPLATE,
    COMMAND_TEST_TEMPLATE,
    NAME_RE,
)


def _backend_available() -> bool:
    """Check if backend-lib shared library exists in this repo."""
    try:
        return (get_root_dir() / "tools" / "shared" / "backend-lib").is_dir()
    except SystemExit:
        return False


_BACKEND_AVAILABLE = _backend_available()

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

CLI_PY_TEMPLATE = """\
\"\"\"{tool_name} CLI.\"\"\"

import os
{backend_stdlib_imports}from importlib.metadata import version as pkg_version
from pathlib import Path

import click
import tomllib
{backend_imports}
# [auto] scaffold:imports — insertion point
from commands import (
    {cmd_underscored},
)

DIST_NAME = "{package_name}"
{required_vars}
_help = "{tool_name} developer tool."
{env_aware_help}

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
    click.echo(f"{binary_name} {{version}}{{suffix}}")
    ctx.exit()


@click.group(help=_help, context_settings={{"help_option_names": ["-h", "--help"]}})
@click.option("--version", is_flag=True, callback=_show_version,
              expose_value=False, is_eager=True, help="Show version")
def cli():
    {cli_body}


# [auto] scaffold:commands — insertion point
cli.add_command({cmd_underscored}.{cmd_underscored}_cmd, name="{cmd_hyphenated}")
{repl_block}

if __name__ == "__main__":
    cli(prog_name="{binary_name}")
"""

CLI_PY_REPL_BLOCK = """

import asyncio
import shlex

from display_lib.output import error
from repl_lib import Repl


# [auto] scaffold:repl-commands — insertion point
_CLICK_COMMANDS = {{
    "{cmd_hyphenated}": {cmd_underscored}.{cmd_underscored}_cmd,
}}


async def _dispatch(cmd_name, line, state):
    click_cmd = _CLICK_COMMANDS.get(cmd_name)
    if not click_cmd:
        error(f"Unknown command: {{cmd_name}}")
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
    name="{tool_name}",
    dispatch=_dispatch,
    initial_state={{}},
    commands=_CLICK_COMMANDS,
    history_file=".{tool_name}_history",
)


@cli.command()
@click.pass_context
def interactive(ctx):
    \"\"\"Start interactive session.\"\"\"
    asyncio.run(_repl.run())
"""

COMMANDS_INIT_TEMPLATE = """\
\"\"\"{tool_name} commands.\"\"\"
"""

PATHS_PY_TEMPLATE = '''"""Path resolution for {tool_name}.

All path logic lives here. Derived paths call get_root_dir() as their base.
"""

import os
import sys
from pathlib import Path

from display_lib.output import error


def get_root_dir() -> Path:
    """Get the project root directory from CLI_ROOT_DIR environment variable.

    In dev mode, the bash wrapper sets this automatically.
    For standalone CLIs, the user must export it.
    """
    root_dir = os.environ.get("CLI_ROOT_DIR")
    if not root_dir:
        error(
            "CLI_ROOT_DIR not set.\\n"
            "  Export CLI_ROOT_DIR, or use the bash wrapper ./tools/{tool_name} if present."
        )
        sys.exit(1)
    root_path = Path(root_dir)
    if not root_path.is_dir():
        error(f"CLI_ROOT_DIR is not a valid directory: {{root_dir}}")
        sys.exit(1)
    return root_path
'''

PYPROJECT_TEMPLATE = """\
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
{dependencies}
]

[project.scripts]
{binary_name} = "cli:cli"

[dependency-groups]
dev = [
    "pytest>=8.2,<9",
    "ruff>=0.4,<1",
    "test-lib>=0.1.0,<1",
]

[tool.uv.sources]
{uv_sources}

[tool.setuptools]
packages = ["commands", "lib", "data"]
py-modules = ["cli"]

[tool.setuptools.package-data]
data = ["**/*"]

[tool.coverage.run]
omit = ["tests/*"]
"""

WRAPPER_TEMPLATE = """\
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOL_DIR="$SCRIPT_DIR/{dir_name}"

export TOOL_EXEC_MODE=dev-source
export PATH="$SCRIPT_DIR:$PATH"
export CLI_ROOT_DIR="${{CLI_ROOT_DIR:-$(dirname "$SCRIPT_DIR")}}"
{env_exports}exec "$TOOL_DIR/.venv/bin/python" "$TOOL_DIR/cli.py" "$@"
"""

CONFTEST_TEMPLATE = """\
\"\"\"Root test configuration for {package_name}.\"\"\"
{env_defaults}

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")
"""

CHANGELOG_TEMPLATE = """\
# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [0.1.0] - {date}

**FEAT:** *initial-release*

Initial scaffolded tool.
"""

TEST_CLI_TEMPLATE = """\
\"\"\"Smoke tests for {binary_name} CLI.\"\"\"

from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from click.testing import CliRunner
from cli import cli
from test_lib.cli import assert_cli_ok


def test_version():
    \"\"\"CLI --version flag prints version string.\"\"\"
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert_cli_ok(result)
    assert "{binary_name}" in result.output


def test_help():
    \"\"\"CLI --help shows available commands.\"\"\"
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert_cli_ok(result)
    assert "{cmd_hyphenated}" in result.output


def test_version_from_pyproject():
    \"\"\"Version falls back to pyproject.toml when package not installed.\"\"\"
    runner = CliRunner()
    with patch("cli.pkg_version", side_effect=PackageNotFoundError()):
        result = runner.invoke(cli, ["--version"])
    assert_cli_ok(result)
    assert "{binary_name}" in result.output
"""


# ---------------------------------------------------------------------------
# Template expansion
# ---------------------------------------------------------------------------


def _expand_cli_py(
    name: str,
    command_name: str,
    include_backend: bool,
    include_repl: bool,
) -> str:
    cmd_underscored = command_name.replace("-", "_")

    if include_backend:
        backend_stdlib_imports = "import sys\n"
        backend_imports = "from backend_lib.env import check_env\n"
        required_vars = 'REQUIRED_VARS = ["CLI_ROOT_DIR", "CLI_BACKEND_URL", "CLI_AGENTIC_BACKEND_URL"]\n'
        env_aware_help = (
            'if os.getenv("TOOL_EXEC_MODE") != "dev-source":\n'
            """    _help += f"\\n\\nEnvironment: {', '.join(REQUIRED_VARS)}"\n"""
        )
        cli_body = (
            'if "--help" not in sys.argv and "-h" not in sys.argv and len(sys.argv) > 1:\n'
            f'        check_env("{name}", REQUIRED_VARS)'
        )
    else:
        backend_stdlib_imports = ""
        backend_imports = ""
        required_vars = ""
        env_aware_help = ""
        cli_body = "pass"

    if include_repl:
        repl_block = CLI_PY_REPL_BLOCK.format(
            tool_name=name,
            cmd_underscored=cmd_underscored,
            cmd_hyphenated=command_name,
        )
    else:
        repl_block = ""

    return CLI_PY_TEMPLATE.format(
        tool_name=name,
        binary_name=name,
        package_name=f"{name}-src",
        backend_stdlib_imports=backend_stdlib_imports,
        backend_imports=backend_imports,
        required_vars=required_vars,
        env_aware_help=env_aware_help,
        cli_body=cli_body,
        cmd_underscored=cmd_underscored,
        cmd_hyphenated=command_name,
        repl_block=repl_block,
    )


def _expand_pyproject(name: str, include_backend: bool, include_repl: bool) -> str:
    deps = ['    "display-lib>=3.0.0,<4",']
    sources = ['display-lib = { path = "../shared/display-lib", editable = true }']

    if include_backend:
        deps.append('    "backend-lib>=1.0.0,<2",')
        sources.append(
            'backend-lib = { path = "../shared/backend-lib", editable = true }'
        )

    if include_repl:
        deps.append('    "repl-lib>=1.0.0,<2",')
        sources.append('repl-lib = { path = "../shared/repl-lib", editable = true }')

    sources.append('test-lib = { path = "../shared/test-lib", editable = true }')

    deps.append('    "click>=8,<9",')

    return PYPROJECT_TEMPLATE.format(
        package_name=f"{name}-src",
        binary_name=name,
        dependencies="\n".join(deps),
        uv_sources="\n".join(sources),
    )


def _expand_wrapper(name: str, include_backend: bool) -> str:
    if include_backend:
        env_exports = (
            'export CLI_BACKEND_URL="${CLI_BACKEND_URL:-http://localhost:8000}"\n'
            'export CLI_AGENTIC_BACKEND_URL="${CLI_AGENTIC_BACKEND_URL:-http://localhost:8001}"\n'
            'export CLI_AGENTIC_BACKEND_WS_URL="${CLI_AGENTIC_BACKEND_WS_URL:-ws://localhost:8001}"\n'
        )
    else:
        env_exports = ""

    return WRAPPER_TEMPLATE.format(
        dir_name=f"{name}-src",
        env_exports=env_exports,
    )


def _expand_conftest(name: str, include_backend: bool) -> str:
    if include_backend:
        env_defaults = (
            "import os\n\n"
            'os.environ.setdefault("CLI_ROOT_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n'
            'os.environ.setdefault("AGENT_STREAM_JWT_SECRET", "test-secret-for-unit-tests-ok!32")\n'
            'os.environ.setdefault("CLI_BACKEND_URL", "http://localhost:8000")\n'
            'os.environ.setdefault("CLI_AGENTIC_BACKEND_URL", "http://localhost:8001")\n'
            'os.environ.setdefault("CLI_AGENTIC_BACKEND_WS_URL", "ws://localhost:8001")\n'
        )
    else:
        env_defaults = ""

    return CONFTEST_TEMPLATE.format(
        package_name=f"{name}-src",
        env_defaults=env_defaults,
    )


# ---------------------------------------------------------------------------
# File generation
# ---------------------------------------------------------------------------


def _get_files(
    name: str,
    command_name: str,
    include_backend: bool,
    include_repl: bool,
) -> list[tuple[str, str]]:
    """Return list of (relative_path, content) for all scaffold files."""
    dir_name = f"{name}-src"
    today = date.today().isoformat()
    cmd_underscored = command_name.replace("-", "_")

    return [
        (
            f"{dir_name}/cli.py",
            _expand_cli_py(name, command_name, include_backend, include_repl),
        ),
        (
            f"{dir_name}/pyproject.toml",
            _expand_pyproject(name, include_backend, include_repl),
        ),
        (
            f"{dir_name}/commands/__init__.py",
            COMMANDS_INIT_TEMPLATE.format(tool_name=name),
        ),
        (
            f"{dir_name}/commands/{cmd_underscored}.py",
            COMMAND_TEMPLATE.format(cmd_underscored=cmd_underscored),
        ),
        (f"{dir_name}/lib/__init__.py", ""),
        (
            f"{dir_name}/lib/paths.py",
            PATHS_PY_TEMPLATE.format(tool_name=name),
        ),
        (f"{dir_name}/data/__init__.py", ""),
        (
            f"{dir_name}/tests/conftest.py",
            _expand_conftest(name, include_backend),
        ),
        (f"{dir_name}/tests/unit/__init__.py", ""),
        (
            f"{dir_name}/tests/unit/test_cli.py",
            TEST_CLI_TEMPLATE.format(binary_name=name, cmd_hyphenated=command_name),
        ),
        (
            f"{dir_name}/tests/unit/test_{cmd_underscored}.py",
            COMMAND_TEST_TEMPLATE.format(cmd_underscored=cmd_underscored),
        ),
        (f"{dir_name}/CHANGELOG.md", CHANGELOG_TEMPLATE.format(date=today)),
    ]


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command()
@click.argument("tool_name")
@click.argument("command_name")
@click.option("--include-repl", is_flag=True, help="Include REPL interactive session")
@click.option("-n", "--dry-run", is_flag=True, help="List files without creating them")
def tool_cmd(
    tool_name: str,
    command_name: str,
    include_repl: bool,
    dry_run: bool,
    include_backend: bool = False,
) -> None:
    """Scaffold a new CLI tool with an initial command.

    \b
    TOOL_NAME      Binary name (lowercase letters ending in 'cli')
    COMMAND_NAME   Initial command to scaffold
    """
    # Validate tool name
    if not NAME_RE.match(tool_name):
        error(f"Invalid tool name: {tool_name}")
        info("Tool names must be lowercase letters only, ending in 'cli'")
        raise SystemExit(1)

    # Validate command name
    if not COMMAND_NAME_RE.match(command_name):
        error(f"Invalid command name: {command_name}")
        info(
            "Command names must be lowercase letters and hyphens (no leading/trailing hyphens)"
        )
        raise SystemExit(1)

    repo_root = get_root_dir()
    tools_dir = repo_root / "tools"
    src_dir = tools_dir / f"{tool_name}-src"
    wrapper_path = tools_dir / tool_name

    # Check for existing directory/wrapper
    if src_dir.exists():
        error(f"Directory already exists: {src_dir}")
        raise SystemExit(1)
    if wrapper_path.exists():
        error(f"Wrapper already exists: {wrapper_path}")
        raise SystemExit(1)

    files = _get_files(tool_name, command_name, include_backend, include_repl)
    wrapper_content = _expand_wrapper(tool_name, include_backend)

    if dry_run:
        click.echo("Would create:")
        for rel_path, _ in files:
            click.echo(f"  tools/{rel_path}")
        click.echo(
            f"  tools/{tool_name}                          (bash wrapper, chmod +x)"
        )
        click.echo("Would run:")
        click.echo(f"  uv sync --group dev in tools/{tool_name}-src/")
        return

    # Write files
    for rel_path, content in files:
        full_path = tools_dir / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    # Write bash wrapper
    wrapper_path.write_text(wrapper_content)
    wrapper_path.chmod(
        wrapper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )

    # Create venv
    info(f"Creating venv in tools/{tool_name}-src/...")
    result = subprocess.run(
        ["uv", "sync", "--group", "dev"],
        cwd=str(src_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"uv sync failed:\n{result.stderr}")
        raise SystemExit(1)

    # Post-create output
    click.echo()
    success("Created:")
    click.echo(f"  tools/{tool_name}-src/  ({len(files)} files + .venv)")
    click.echo(f"  tools/{tool_name}        (bash wrapper)")
    click.echo()
    info("Optional: add this line to CLI_TOOLS in scripts/run-tests.sh")
    click.echo(f'    "{tool_name}"')
    click.echo()
    info("Verify:")
    click.echo(f"  ./tools/{tool_name} --version")


if _BACKEND_AVAILABLE:
    tool_cmd = click.option(
        "--include-backend",
        is_flag=True,
        help="Add backend business logic, env vars and dependencies",
    )(tool_cmd)
