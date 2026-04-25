"""mint command — create mutated file with valid checksum."""

import os
import zlib
from pathlib import Path

import click

from display_lib.output import success

from lib.display import print_result_block


@click.command()
@click.option("--file", "file_path", metavar="FILE", help="Binary file to mutate.")
@click.option("--output", "-o", metavar="FILE", help="Output file path.")
@click.option(
    "--checksum-offset",
    type=int,
    required=True,
    metavar="OFFSET",
    help="Byte offset of checksum (4-byte CRC32).",
)
def mint_cmd(
    file_path: str | None,
    output: str | None,
    checksum_offset: int,
) -> None:
    """Create a mutated copy with a recalculated valid checksum."""
    file_path = file_path or os.getenv("HEXSIR_FILE")
    if not file_path:
        raise click.UsageError("FILE not provided and HEXSIR_FILE is not set.")

    input_path = Path(file_path)
    data = bytearray(input_path.read_bytes())

    body_offset = checksum_offset + 4

    if len(data) < body_offset + 1:
        raise click.ClickException("File too small for checksum at this offset.")

    output_path = (
        Path(output)
        if output
        else input_path.with_name(f"{input_path.stem}.mint{input_path.suffix}")
    )

    # Read original checksum
    original_checksum = int.from_bytes(
        data[checksum_offset : checksum_offset + 4], "little"
    )

    # Mutate first byte of body
    mutate_offset = body_offset
    original_byte = data[mutate_offset]
    mutated_byte = original_byte ^ 0x01
    data[mutate_offset] = mutated_byte

    # Compute new checksum for modified body
    new_checksum = zlib.crc32(data[body_offset:]) & 0xFFFFFFFF

    # Write new checksum
    data[checksum_offset : checksum_offset + 4] = new_checksum.to_bytes(4, "little")

    output_path.write_bytes(data)

    success("Minted file created.")
    print_result_block(
        "Mint",
        [
            (
                "mutated_byte",
                f"byte {mutate_offset}: 0x{original_byte:02X} → 0x{mutated_byte:02X}",
            ),
            ("checksum", f"0x{original_checksum:08X} → 0x{new_checksum:08X}"),
        ],
    )
