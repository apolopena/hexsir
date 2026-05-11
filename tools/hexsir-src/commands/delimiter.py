"""delimiter command — find delimiter patterns at a specific offset."""

import os
from pathlib import Path

import click

from display_lib.output import info

from lib.display import print_result_block
from lib.encoding import DELIMITER_PATTERNS, SUPPORTED_ENCODINGS, encode_delimiter


@click.command()
@click.option("--file", "file_path", metavar="FILE", help="Binary file to search.")
@click.option(
    "--after",
    required=True,
    metavar="OFFSET",
    help="Offset to search after.",
)
@click.option(
    "--encoding",
    required=True,
    type=click.Choice(SUPPORTED_ENCODINGS),
    help="Text encoding.",
)
def delimiter_cmd(file_path: str | None, after: str, encoding: str) -> None:
    """Find delimiter patterns at a specific offset."""
    file_path = file_path or os.getenv("HEXSIR_FILE")
    if not file_path:
        raise click.UsageError("FILE not provided and HEXSIR_FILE is not set.")

    after_offset = int(after, 0)
    data = Path(file_path).read_bytes()

    if after_offset < 0 or after_offset >= len(data):
        raise click.UsageError("after offset is outside file bounds.")

    found = False

    for raw in DELIMITER_PATTERNS:
        pattern = encode_delimiter(raw, encoding)

        if data[after_offset : after_offset + len(pattern)] == pattern:
            start = after_offset
            end = start + len(pattern)

            print_result_block(
                "Delimiter Match",
                [
                    ("delimiter", repr(raw)),
                    ("encoding", encoding),
                    ("start", f"0x{start:x}"),
                    ("end", f"0x{end:x}"),
                ],
            )

            found = True

    if not found:
        info("No delimiter matches found.")
        print_result_block(
            "Search",
            [
                ("after", f"0x{after_offset:x}"),
                ("encoding", encoding),
            ],
        )
