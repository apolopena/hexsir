"""attach command — attach the shim to a running game process."""

import click

from display_lib.output import error, success
from tree_lib import tree_fail, tree_group, tree_ok

from lib import config, shim_client
from lib.errors import ShimError, ShimRPCError, ShimUnreachable


@click.command()
@click.option(
    "--process",
    "-p",
    "process_name",
    default="Ravenswatch.exe",
    show_default=True,
    help="Game process to attach to.",
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
def attach_cmd(
    process_name: str,
    shim_host: str | None,
    shim_port: int | None,
    verbose: bool,
) -> dict | None:
    """Attach the shim to a running game process."""
    if verbose:
        return _attach_verbose(process_name, shim_host, shim_port)
    return _attach_quiet(process_name, shim_host, shim_port)


def _attach_quiet(
    process_name: str,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    try:
        result = shim_client.call(
            "attach",
            params={"process": process_name},
            host=shim_host,
            port=shim_port,
        )
    except ShimError as e:
        error(str(e))
        return None
    success(f"Attached to {result['process']} (PID {result['pid']})")
    return result


def _attach_verbose(
    process_name: str,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    tree_group("attach")

    # Step 1: resolve host
    try:
        host = config.shim_host(shim_host)
        port = config.shim_port(shim_port)
    except ShimError as e:
        tree_fail(f"resolve shim host: {e}", is_last=True)
        return None
    tree_ok(f"resolve shim host: {host}:{port}")

    # Step 2: ping
    try:
        ping = shim_client.call("ping", host=host, port=port)
    except ShimUnreachable as e:
        tree_fail(f"ping shim: {e}", is_last=True)
        return None
    except ShimError as e:
        tree_fail(f"ping shim: {e}", is_last=True)
        return None
    state = "attached" if ping.get("attached") else "idle"
    tree_ok(f"ping shim: {state}")

    # Step 3: attach RPC
    try:
        result = shim_client.call(
            "attach",
            params={"process": process_name},
            host=host,
            port=port,
        )
    except ShimRPCError as e:
        tree_fail(f"attach {process_name}: {e}", is_last=True)
        return None
    except ShimError as e:
        tree_fail(f"attach {process_name}: {e}", is_last=True)
        return None
    tree_ok(
        f"attach {process_name}: PID {result['pid']}, "
        f"base {result['process_base']:#018x}"
    )

    # Step 4: verify
    try:
        verify = shim_client.call("ping", host=host, port=port)
    except ShimError as e:
        tree_fail(f"verify state: {e}", is_last=True)
        return None
    if verify.get("attached"):
        tree_ok("verify state: attached", is_last=True)
        return result
    tree_fail("verify state: shim says not attached", is_last=True)
    return None
