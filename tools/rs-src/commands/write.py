"""write command — write a typed value to a memory address via the shim.

No confirmation prompt. The shim has no transactional rollback — callers
must verify the address themselves before invoking. ``rs read`` first if
unsure.
"""

import click

from display_lib.output import error, success
from tree_lib import tree_fail, tree_group, tree_ok

from lib import config, shim_client, value_codec
from lib.errors import ShimError


@click.command()
@click.argument("addr", type=str)
@click.argument("value", type=str)
@click.option(
    "--as",
    "as_type",
    type=click.Choice(value_codec.TYPE_NAMES),
    default="hex",
    show_default=True,
    metavar="TYPE",
    help="Encode the value as this type before writing.",
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
def write_cmd(
    addr: str,
    value: str,
    as_type: str,
    shim_host: str | None,
    shim_port: int | None,
    verbose: bool,
) -> dict | None:
    """Write VALUE to memory at ADDR (hex with 0x prefix, or decimal).

    No confirmation. Use ``rs read`` first if you want to verify the
    target before overwriting.
    """
    try:
        addr_int = value_codec.parse_addr(addr)
    except ValueError as e:
        error(f"invalid address: {e}")
        return None
    try:
        data = value_codec.encode(value, as_type)
    except ValueError as e:
        error(str(e))
        return None
    if verbose:
        return _write_verbose(addr_int, data, as_type, value, shim_host, shim_port)
    return _write_quiet(addr_int, data, as_type, value, shim_host, shim_port)


def _write_quiet(
    addr: int,
    data: bytes,
    as_type: str,
    value_repr: str,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    try:
        result = shim_client.call(
            "write",
            params={"addr": addr, "data_hex": data.hex()},
            host=shim_host,
            port=shim_port,
        )
    except ShimError as e:
        error(str(e))
        return None
    n = result.get("written", len(data))
    success(f"0x{addr:x} ({n} bytes, {as_type}) <- {value_repr}")
    return {"addr": addr, "written": n, "type": as_type, "raw": data.hex()}


def _write_verbose(
    addr: int,
    data: bytes,
    as_type: str,
    value_repr: str,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    tree_group("write")

    try:
        host = config.shim_host(shim_host)
        port = config.shim_port(shim_port)
    except ShimError as e:
        tree_fail(f"resolve shim host: {e}", is_last=True)
        return None
    tree_ok(f"resolve shim host: {host}:{port}")

    tree_ok(f"encode {value_repr!r} as {as_type}: {data.hex()} ({len(data)} bytes)")

    try:
        result = shim_client.call(
            "write",
            params={"addr": addr, "data_hex": data.hex()},
            host=host,
            port=port,
        )
    except ShimError as e:
        tree_fail(f"write 0x{addr:x}: {e}", is_last=True)
        return None
    n = result.get("written", len(data))
    tree_ok(f"write 0x{addr:x}: {n} bytes", is_last=True)
    return {"addr": addr, "written": n, "type": as_type, "raw": data.hex()}
