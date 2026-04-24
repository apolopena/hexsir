"""verify command — validate suspected checksum location via mutation."""

import zlib

import click

from display_lib.output import error, header, info, success

from lib.checksum import read_file_bytes


@click.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=str))
@click.option(
    "--offset",
    default=12,
    type=int,
    show_default=True,
    metavar="BYTES",
    help="Byte offset where 4-byte checksum is located.",
)
def verify_cmd(file: str, offset: int) -> None:
    """Validate checksum location by flipping one byte and checking for mismatch."""
    data = read_file_bytes(file)

    checksum_offset = offset
    body_offset = offset + 4

    if len(data) < body_offset + 4:
        raise click.ClickException(
            "File too small to validate checksum at this offset."
        )

    header(f"Verifying {file}")
    info(f"Checksum offset: {checksum_offset}, Body offset: {body_offset}")

    stored_original = int.from_bytes(
        data[checksum_offset : checksum_offset + 4], "little"
    )
    computed_original = zlib.crc32(data[body_offset:]) & 0xFFFFFFFF

    info(f"Stored:   0x{stored_original:08X}")
    info(f"Computed: 0x{computed_original:08X}")

    if stored_original != computed_original:
        print()
        error("Baseline mismatch - checksum does not match at this location")
        print()
        header("Summary")
        error("NOT VERIFIED (baseline mismatch)")
        return

    mutated = bytearray(data)
    mutated[body_offset] ^= 0x01

    computed_mutated = zlib.crc32(mutated[body_offset:]) & 0xFFFFFFFF

    info(f"Mutated:  0x{computed_mutated:08X}")

    print()
    header("Summary")
    if computed_mutated != stored_original:
        success("VERIFIED - mutation caused expected mismatch")
    else:
        error("NOT VERIFIED - mutation did not change checksum")
