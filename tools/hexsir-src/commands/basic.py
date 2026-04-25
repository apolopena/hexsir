"""basic command — check whole file with no header shift."""

import click

from lib.checksum import analyze_region, read_file_bytes
from lib.display import print_match_summary


@click.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=str))
def basic_cmd(file: str) -> None:
    """Check whole file with no header shift."""
    data = read_file_bytes(file)
    matches = analyze_region(data, "whole file")
    print_match_summary(matches)
