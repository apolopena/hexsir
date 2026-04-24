"""scan command — scan multiple header shifts."""

import click

from lib.checksum import analyze_region, print_summary, read_file_bytes


@click.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=str))
@click.option("--start", default=0, type=int, show_default=True, metavar="OFFSET")
@click.option("--stop", default=64, type=int, show_default=True, metavar="OFFSET")
@click.option("--step", default=4, type=int, show_default=True, metavar="BYTES")
def scan_cmd(file: str, start: int, stop: int, step: int) -> None:
    """Scan multiple header shifts."""
    data = read_file_bytes(file)

    if start < 0:
        raise click.ClickException("start cannot be negative.")
    if stop < 0:
        raise click.ClickException("stop cannot be negative.")
    if step <= 0:
        raise click.ClickException("step must be greater than 0.")
    if start > stop:
        raise click.ClickException("start cannot be greater than stop.")

    all_matches = []
    seen = set()
    for offset in range(start, stop + 1, step):
        if offset >= len(data):
            break

        label = f"header shift = {offset} bytes"
        if label in seen:
            continue
        seen.add(label)

        matches = analyze_region(data[offset:], label)
        all_matches.extend(matches)

    print_summary(all_matches)
