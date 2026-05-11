"""read command — read a typed value from a memory address via the shim."""

import click

from display_lib.output import error, success
from tree_lib import tree_fail, tree_group, tree_ok

from lib import config, shim_client, value_codec
from lib.errors import ShimError


@click.command()
@click.argument("addr", type=str)
@click.option(
    "--length",
    "-n",
    type=int,
    default=None,
    metavar="N",
    help="Bytes to read (default: type's natural size; 4 for hex).",
)
@click.option(
    "--as",
    "as_type",
    type=click.Choice(value_codec.TYPE_NAMES),
    default="hex",
    show_default=True,
    metavar="TYPE",
    help="Decode the bytes as this type.",
)
@click.option(
    "--shim-host",
    "shim_host",
    default=None,
    help="Override RS_SHIM_HOST.",
)
@click.option(
    "--shim-port",
    "shim_port",
    default=None,
    type=int,
    help="Override RS_SHIM_PORT.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Print each step as a tree.",
)
def read_cmd(
    addr: str,
    length: int | None,
    as_type: str,
    shim_host: str | None,
    shim_port: int | None,
    verbose: bool,
) -> dict | None:
    """Read a typed value from memory ADDR (hex with 0x prefix, or decimal)."""
    try:
        addr_int = value_codec.parse_addr(addr)
    except ValueError as e:
        error(f"invalid address: {e}")
        return None
    n = value_codec.default_length(as_type, length)
    if verbose:
        return _read_verbose(addr_int, n, as_type, shim_host, shim_port)
    return _read_quiet(addr_int, n, as_type, shim_host, shim_port)


def _read_quiet(
    addr: int,
    length: int,
    as_type: str,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    try:
        result = shim_client.call(
            "read",
            params={"addr": addr, "length": length},
            host=shim_host,
            port=shim_port,
        )
    except ShimError as e:
        error(str(e))
        return None
    raw = bytes.fromhex(result)
    try:
        decoded = value_codec.decode(raw, as_type)
    except ValueError as e:
        error(str(e))
        return None
    formatted = value_codec.format_value(decoded, as_type)
    success(f"0x{addr:x} ({length} bytes, {as_type}) = {formatted}")
    return {
        "addr": addr,
        "length": length,
        "type": as_type,
        "raw": raw.hex(),
        "value": decoded,
    }


def _read_verbose(
    addr: int,
    length: int,
    as_type: str,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    tree_group("read")

    try:
        host = config.shim_host(shim_host)
        port = config.shim_port(shim_port)
    except ShimError as e:
        tree_fail(f"resolve shim host: {e}", is_last=True)
        return None
    tree_ok(f"resolve shim host: {host}:{port}")

    try:
        result = shim_client.call(
            "read",
            params={"addr": addr, "length": length},
            host=host,
            port=port,
        )
    except ShimError as e:
        tree_fail(f"read 0x{addr:x} ({length} bytes): {e}", is_last=True)
        return None
    raw = bytes.fromhex(result)
    tree_ok(f"read 0x{addr:x}: {length} bytes (raw={raw.hex()})")

    try:
        decoded = value_codec.decode(raw, as_type)
    except ValueError as e:
        tree_fail(f"decode as {as_type}: {e}", is_last=True)
        return None
    formatted = value_codec.format_value(decoded, as_type)
    tree_ok(f"decode as {as_type}: {formatted}", is_last=True)
    return {
        "addr": addr,
        "length": length,
        "type": as_type,
        "raw": raw.hex(),
        "value": decoded,
    }
