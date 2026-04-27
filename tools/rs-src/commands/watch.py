"""watch command — poll a memory address over a persistent shim connection.

Holds one TCP socket open for the duration of the run, multiplexing all
reads over it. Default behaviour prints a baseline row then prints only
when the value changes; ``--all`` prints every tick.
"""

import time

import click

from display_lib.output import error, info, success
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
    "--interval",
    "-i",
    type=float,
    default=0.5,
    show_default=True,
    metavar="S",
    help="Seconds between polls.",
)
@click.option(
    "--duration",
    "-d",
    type=float,
    default=60.0,
    show_default=True,
    metavar="S",
    help="Total polling window in seconds.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Print every tick (default: print only on value change).",
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
    help="Print each step as a tree (only setup phase; samples follow).",
)
def watch_cmd(
    addr: str,
    length: int | None,
    as_type: str,
    interval: float,
    duration: float,
    show_all: bool,
    shim_host: str | None,
    shim_port: int | None,
    verbose: bool,
) -> dict | None:
    """Poll memory at ADDR over a persistent shim connection."""
    try:
        addr_int = value_codec.parse_addr(addr)
    except ValueError as e:
        error(f"invalid address: {e}")
        return None
    if interval <= 0:
        error("interval must be > 0")
        return None
    if duration <= 0:
        error("duration must be > 0")
        return None
    n = value_codec.default_length(as_type, length)

    if verbose:
        return _watch_verbose(
            addr_int, n, as_type, interval, duration, show_all, shim_host, shim_port
        )
    return _watch_quiet(
        addr_int, n, as_type, interval, duration, show_all, shim_host, shim_port
    )


def _watch_quiet(
    addr: int,
    length: int,
    as_type: str,
    interval: float,
    duration: float,
    show_all: bool,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    info(
        f"watching 0x{addr:x} ({length} bytes, {as_type}) "
        f"every {interval}s for {duration}s"
        + (" — all ticks" if show_all else " — on change only")
    )
    return _run_loop(
        addr, length, as_type, interval, duration, show_all, shim_host, shim_port
    )


def _watch_verbose(
    addr: int,
    length: int,
    as_type: str,
    interval: float,
    duration: float,
    show_all: bool,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    tree_group("watch")
    try:
        host = config.shim_host(shim_host)
        port = config.shim_port(shim_port)
    except ShimError as e:
        tree_fail(f"resolve shim host: {e}", is_last=True)
        return None
    tree_ok(f"resolve shim host: {host}:{port}")
    tree_ok(
        f"target: 0x{addr:x} ({length} bytes, {as_type}); "
        f"interval={interval}s, duration={duration}s",
        is_last=True,
    )
    return _run_loop(addr, length, as_type, interval, duration, show_all, host, port)


def _run_loop(
    addr: int,
    length: int,
    as_type: str,
    interval: float,
    duration: float,
    show_all: bool,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    last_value: object = None
    samples = 0
    changes = 0
    try:
        with shim_client.Session(host=shim_host, port=shim_port) as session:
            t0 = time.monotonic()
            value = _read_one(session, addr, length, as_type)
            formatted_baseline = value_codec.format_value(value, as_type)
            click.echo(f"  t=0.0s  0x{addr:x} = {formatted_baseline}  (baseline)")
            last_value = value
            samples = 1

            while True:
                elapsed = time.monotonic() - t0
                if elapsed >= duration:
                    break
                time.sleep(interval)
                elapsed = time.monotonic() - t0
                value = _read_one(session, addr, length, as_type)
                samples += 1
                if show_all or value != last_value:
                    formatted = value_codec.format_value(value, as_type)
                    delta = ""
                    if value != last_value:
                        changes += 1
                        delta = " *"
                    click.echo(f"  t={elapsed:.1f}s  0x{addr:x} = {formatted}{delta}")
                last_value = value
    except (ShimError, ValueError) as e:
        error(str(e))
        return None
    except KeyboardInterrupt:
        info("interrupted")
    success(f"{samples} sample(s), {changes} change(s)")
    return {
        "addr": addr,
        "length": length,
        "type": as_type,
        "samples": samples,
        "changes": changes,
        "last": last_value,
    }


def _read_one(session, addr: int, length: int, as_type: str) -> object:
    result = session.call("read", {"addr": addr, "length": length})
    raw = bytes.fromhex(result)
    return value_codec.decode(raw, as_type)
