"""decipher command."""

import click

from display_lib.output import success
from lib.cipher import decipher


@click.command()
@click.argument("text")
def decipher_cmd(text: str) -> None:
    """Decode ciphered filename to plaintext."""
    result = decipher(text)
    success(result)
