"""audit command."""

import click

from display_lib.output import info, success


@click.command()
def audit_cmd() -> None:
    """TODO: describe this command."""
    info("Running audit...")
    success("Done")
