"""cipher command."""

import click

from display_lib.output import success
from lib.cipher import encipher, encipher_path


@click.command()
@click.argument("text")
@click.option(
    "-p",
    "--path-aware",
    is_flag=True,
    help="Preserve path text through DarkTalesResources/_Cooking/ and encode only the cooked suffix.",
)
def cipher_cmd(text: str, path_aware: bool) -> None:
    """Encode plaintext to ciphered text."""
    result = encipher_path(text) if path_aware else encipher(text)
    success(result)
