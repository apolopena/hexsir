"""Browse Ravenswatch cooked game assets."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import threading

import click

from commands.harvest import harvest_group
from lib.cipher import COOKING_MARKER
from lib.game_assets import display_game_asset_path, resolve_game_asset_path


@contextmanager
def _spinner(message: str, *, enabled: bool):
    if not enabled:
        yield
        return

    stop = threading.Event()
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def run() -> None:
        idx = 0
        while not stop.is_set():
            sys.stderr.write(f"\r{frames[idx % len(frames)]} {message}")
            sys.stderr.flush()
            idx += 1
            stop.wait(0.08)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        sys.stderr.write("\r" + " " * (len(message) + 4) + "\r")
        sys.stderr.flush()


@click.group(name="game-assets")
def game_assets_group() -> None:
    """Browse and manage cooked game assets."""


def _split_path_and_ls_args(tokens: tuple[str, ...]) -> tuple[str, list[str]]:
    if not tokens:
        return "", []
    for index, token in enumerate(tokens):
        if not token.startswith("-"):
            return token, [*tokens[:index], *tokens[index + 1 :]]
    return "", list(tokens)


def _rewrite_ls_output(
    text: str,
    target: Path,
    *,
    raw: bool,
    full: bool,
    cooked_relative: bool,
    truncate_paths: bool,
) -> str:
    paths = [target]
    if target.is_dir():
        paths.extend(target.iterdir())

    replacements: dict[str, str] = {}
    for path in paths:
        display = display_game_asset_path(
            path,
            raw=raw,
            full=full,
            cooked_relative=cooked_relative,
            truncate_prefix=truncate_paths,
        )
        replacements[path.as_posix()] = display
        replacements[path.name] = display

    rewritten = text
    for source in sorted(replacements, key=len, reverse=True):
        if source:
            rewritten = rewritten.replace(source, replacements[source])
    return rewritten


@click.command(
    name="ls",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("tokens", nargs=-1, type=click.UNPROCESSED)
@click.option(
    "--ciphered",
    is_flag=True,
    help="Treat PATH as already ciphered instead of decoded.",
)
@click.option("--raw", is_flag=True, help="Print ciphered asset names.")
@click.option(
    "--cooked-relative",
    is_flag=True,
    help="Print paths relative to DarkTalesResources/_Cooking.",
)
@click.option(
    "-t",
    "--truncate-paths",
    is_flag=True,
    help="Collapse full install paths to .../_Cooking/...",
)
@click.option("-l", "--long", "long_format", is_flag=True, help="Use long listing format.")
@click.option("-a", "--all", "all_entries", is_flag=True, help="Include hidden entries.")
@click.option(
    "--full",
    is_flag=True,
    help="Print full cooked asset paths. Inferred when PATH is a full cooked path.",
)
@click.option(
    "--cooking-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    hidden=True,
)
def ls_cmd(
    tokens: tuple[str, ...],
    *,
    ciphered: bool,
    raw: bool,
    cooked_relative: bool,
    truncate_paths: bool,
    long_format: bool,
    all_entries: bool,
    full: bool,
    cooking_root,
) -> None:
    """List entries from cooked game assets."""
    path, ls_args = _split_path_and_ls_args(tokens)
    full = full or COOKING_MARKER in path.replace("\\", "/")
    try:
        show_spinner = sys.stderr.isatty()
        with _spinner("listing cooked assets...", enabled=show_spinner):
            target = resolve_game_asset_path(
                path,
                cooking_root=cooking_root,
                query_is_ciphered=ciphered,
            )
            if long_format:
                ls_args.append("-l")
            if all_entries:
                ls_args.append("-a")
            result = subprocess.run(
                ["ls", *ls_args, target.as_posix()],
                capture_output=True,
                text=True,
                check=False,
            )
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    stdout = _rewrite_ls_output(
        result.stdout,
        target,
        raw=raw,
        full=full,
        cooked_relative=cooked_relative,
        truncate_paths=truncate_paths,
    )
    stderr = _rewrite_ls_output(
        result.stderr,
        target,
        raw=raw,
        full=full,
        cooked_relative=cooked_relative,
        truncate_paths=truncate_paths,
    )
    if stdout:
        click.echo(stdout, nl=False)
    if stderr:
        click.echo(stderr, nl=False, err=True)
    if result.returncode:
        raise click.exceptions.Exit(result.returncode)


game_assets_group.add_command(ls_cmd, name="ls")
game_assets_group.add_command(harvest_group, name="harvest")
