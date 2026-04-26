"""Developer maintenance commands (synced under `rs dev ...`)."""

import click

from . import sync_shim


@click.group(name="dev")
def dev_group():
    """Developer maintenance commands."""


dev_group.add_command(sync_shim.sync_shim_cmd, name="sync-shim")
