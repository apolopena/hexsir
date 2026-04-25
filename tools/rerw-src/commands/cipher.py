"""cipher command."""

import click

from display_lib.output import success
from lib.cipher import encipher


@click.command()
@click.argument("text")
def cipher_cmd(text: str) -> None:
    """Encode plaintext to ciphered filename."""
    result = encipher(text)
    success(result)
