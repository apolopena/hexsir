"""detach command — release the shim's attachment to the game process."""

import click

from display_lib.output import error, success

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
def detach_cmd(shim_host: str | None, shim_port: int | None) -> dict | None:
    """Release the shim's attachment to the game process."""
    try:
        result = shim_client.call("detach", host=shim_host, port=shim_port)
    except ShimError as e:
        error(str(e))
        return None
    success("Detached")
    return result
