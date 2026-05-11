"""status command — show shim/attach state."""

import click

from display_lib.output import error, info, success

from lib import shim_client
from lib.errors import ShimError


@click.command()
@click.option(
    "--shim-host",
    "shim_host",
    default=None,
    help="Override RS_SHIM_HOST.",
)
@click.option(
    "--shim-port",
    "shim_port",
    default=None,
    type=int,
    help="Override RS_SHIM_PORT.",
)
def status_cmd(shim_host: str | None, shim_port: int | None) -> dict | None:
    """Show shim and attachment state."""
    try:
        result = shim_client.call("ping", host=shim_host, port=shim_port)
    except ShimError as e:
        error(str(e))
        return None
    if result.get("attached"):
        success(
            f"shim alive — attached to PID {result['pid']}, "
            f"base {result['process_base']:#018x}"
        )
    else:
        info("shim alive — idle (not attached)")
    return result
