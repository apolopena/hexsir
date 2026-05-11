"""find command — scan committed writable heap for a hex byte pattern.

Pass-through to the shim's ``find`` RPC. Output formats:

- Default summary: total count + first ``--limit`` matches inline.
- ``--all``: every match printed inline (escape hatch for power users).
- ``--out FILE``: full list dumped to FILE, one address per line.
"""

from pathlib import Path

import click

from display_lib.output import error, info, success
from tree_lib import tree_fail, tree_group, tree_ok

from lib import config, shim_client
from lib.errors import ShimError


@click.command()
@click.argument("needle_hex", type=str)
@click.option(
    "--alignment",
    "-a",
    type=int,
    default=1,
    show_default=True,
    metavar="N",
    help="Match only on N-byte alignment (e.g. 8 for vtable-aligned scans).",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=20,
    show_default=True,
    metavar="N",
    help="Inline match cap in summary mode. Ignored with --all or --out.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Print every match inline (no truncation).",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    metavar="FILE",
    help="Write full match list to FILE (one address per line).",
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
def find_cmd(
    needle_hex: str,
    alignment: int,
    limit: int,
    show_all: bool,
    out_path: Path | None,
    shim_host: str | None,
    shim_port: int | None,
    verbose: bool,
) -> dict | None:
    """Scan the attached process for matches of NEEDLE_HEX (hex bytes)."""
    needle = needle_hex.replace(" ", "").lower()
    if needle.startswith("0x"):
        needle = needle[2:]
    if len(needle) % 2 != 0:
        error(f"needle hex must be even-length, got {len(needle)} chars")
        return None
    if alignment < 1:
        error("alignment must be >= 1")
        return None

    if verbose:
        return _find_verbose(
            needle, alignment, limit, show_all, out_path, shim_host, shim_port
        )
    return _find_quiet(
        needle, alignment, limit, show_all, out_path, shim_host, shim_port
    )


def _find_quiet(
    needle: str,
    alignment: int,
    limit: int,
    show_all: bool,
    out_path: Path | None,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    try:
        matches = shim_client.call(
            "find",
            params={"needle_hex": needle, "alignment": alignment},
            host=shim_host,
            port=shim_port,
        )
    except ShimError as e:
        error(str(e))
        return None
    _emit_results(matches, limit, show_all, out_path)
    return {"count": len(matches), "matches": matches}


def _find_verbose(
    needle: str,
    alignment: int,
    limit: int,
    show_all: bool,
    out_path: Path | None,
    shim_host: str | None,
    shim_port: int | None,
) -> dict | None:
    tree_group("find")

    try:
        host = config.shim_host(shim_host)
        port = config.shim_port(shim_port)
    except ShimError as e:
        tree_fail(f"resolve shim host: {e}", is_last=True)
        return None
    tree_ok(f"resolve shim host: {host}:{port}")

    tree_ok(f"needle: {needle} ({len(needle) // 2} bytes), alignment={alignment}")

    try:
        matches = shim_client.call(
            "find",
            params={"needle_hex": needle, "alignment": alignment},
            host=host,
            port=port,
        )
    except ShimError as e:
        tree_fail(f"scan: {e}", is_last=True)
        return None
    tree_ok(f"scan: {len(matches)} match(es)", is_last=True)

    _emit_results(matches, limit, show_all, out_path)
    return {"count": len(matches), "matches": matches}


def _emit_results(
    matches: list[int],
    limit: int,
    show_all: bool,
    out_path: Path | None,
) -> None:
    count = len(matches)
    if out_path is not None:
        out_path.write_text("\n".join(f"0x{a:x}" for a in matches) + "\n")
        success(f"{count} match(es); full list -> {out_path}")
        return
    if count == 0:
        info("0 matches")
        return
    if show_all or count <= limit:
        success(f"{count} match(es):")
        for addr in matches:
            click.echo(f"  0x{addr:x}")
        return
    success(f"{count} match(es); first {limit}:")
    for addr in matches[:limit]:
        click.echo(f"  0x{addr:x}")
    info(f"... {count - limit} more (use --all or --out FILE)")
