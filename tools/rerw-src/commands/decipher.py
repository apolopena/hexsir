"""decipher command."""

import click

from display_lib.output import success
from lib.cipher import decipher, decipher_path


@click.command()
@click.argument("text")
@click.option(
    "-p",
    "--path-aware",
    is_flag=True,
    help="Preserve path text through DarkTalesResources/_Cooking/ and decode only the cooked suffix.",
)
def decipher_cmd(text: str, path_aware: bool) -> None:
    """Decode ciphered text to plaintext."""
    result = decipher_path(text) if path_aware else decipher(text)
    success(result)
