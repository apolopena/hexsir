"""key command — search for text patterns in binary files."""

import os
from pathlib import Path

import click

from display_lib.output import info

from lib.display import print_result_block
from lib.encoding import build_key_patterns


@click.command()
@click.argument("key")
@click.option("--file", "file_path", metavar="FILE", help="Binary file to search.")
def key_cmd(key: str, file_path: str | None) -> None:
    """Search for a text key in binary file (ascii and utf16le)."""
    file_path = file_path or os.getenv("HEXSIR_FILE")
    if not file_path:
        raise click.UsageError("FILE not provided and HEXSIR_FILE is not set.")

    data = Path(file_path).read_bytes()
    patterns = build_key_patterns(key)
    found = False

    for encoding, pattern in patterns:
        offset = data.find(pattern)
        while offset != -1:
            start = offset
            end = offset + len(pattern)

            print_result_block(
                "Key Match",
                [
                    ("key", f'"{key}"'),
                    ("encoding", encoding),
                    ("start", f"0x{start:x}"),
                    ("end", f"0x{end:x}"),
                ],
            )

            found = True
            offset = data.find(pattern, offset + 1)

    if not found:
        info("No key matches found.")
        print_result_block(
            "Search",
            [
                ("key", f'"{key}"'),
                ("encodings", ", ".join(e for e, _ in patterns)),
            ],
        )
