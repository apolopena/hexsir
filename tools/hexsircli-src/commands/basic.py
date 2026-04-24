"""basic command — check whole file with no header shift."""

import click

from lib.checksum import analyze_region, print_summary, read_file_bytes


@click.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=str))
def basic_cmd(file: str) -> None:
    """Check whole file with no header shift."""
    data = read_file_bytes(file)
    matches = analyze_region(data, "whole file")
    print_summary(matches)
