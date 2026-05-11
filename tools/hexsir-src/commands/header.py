"""header command — check a single header shift."""

import click

from lib.checksum import analyze_region, read_file_bytes, validate_offset
from lib.display import print_match_summary


@click.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=str))
@click.option(
    "--offset",
    required=True,
    type=int,
    metavar="BYTES",
    help="Skip this many bytes from the beginning.",
)
def header_cmd(file: str, offset: int) -> None:
    """Check a single header shift."""
    data = read_file_bytes(file)
    validate_offset(offset, len(data), "offset")
    matches = analyze_region(data[offset:], f"offset {offset}")
    print_match_summary(matches)
