"""hexsir CLI."""

import os
from importlib.metadata import version as pkg_version
from pathlib import Path

import click
import tomllib

# [auto] scaffold:imports — insertion point
from commands import (
    basic,
    delimiter,
    header,
    key,
    mint,
    scan,
    verify,
)

DIST_NAME = "hexsir-src"

_help = "Probe binary files for checksums and patterns."


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
    click.echo(f"hexsir {version}{suffix}")
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


# --- checksum group ---
@cli.group(name="checksum")
def checksum_():
    """Analyze files for common 4-byte checksums."""
    pass


checksum_.add_command(basic.basic_cmd, name="basic")
checksum_.add_command(header.header_cmd, name="header")
checksum_.add_command(scan.scan_cmd, name="scan")
checksum_.add_command(verify.verify_cmd, name="verify")


# --- probe group ---
@cli.group(name="probe")
def probe_():
    """Search for patterns in binary files."""
    pass


probe_.add_command(key.key_cmd, name="key")
probe_.add_command(delimiter.delimiter_cmd, name="delimiter")


# --- top-level commands ---
# [auto] scaffold:commands — insertion point
cli.add_command(mint.mint_cmd, name="mint")


if __name__ == "__main__":
    cli(prog_name="hexsir")
