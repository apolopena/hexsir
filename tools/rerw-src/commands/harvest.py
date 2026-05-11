"""harvest command group."""

import click

from display_lib.output import info


@click.group(invoke_without_command=True)
@click.pass_context
def harvest_group(ctx) -> None:
    """Harvest and organize game assets."""
    if ctx.invoked_subcommand is None:
        info("Use 'rerw game-assets harvest --help' to see available subcommands")
