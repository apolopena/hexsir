"""game-assets inspect — discovery surface for valid registry keys.

Three subcommands:
  - heroes:  list valid hero keys
  - talents: list valid talent keys for a specific hero
  - items:   list valid magical-item keys

Output is one entry per record, fields one per line, blank line between
entries. Default fields are NAME / KEY / DESCRIPTION (talents and items).
`-n / --no-description` omits DESCRIPTION; `-v / --verbose` adds developer
fields below the default block.
"""

from __future__ import annotations

import click

from display_lib.output import error
from lib import game_registry as registry
from lib.game_registry import RegistryError


def _echo_entry(fields: list[tuple[str, object]]) -> None:
    """Print one entry. Each tuple is (LABEL, value); label is uppercased."""
    for label, value in fields:
        if value is None:
            value = ""
        click.echo(f"{label}: {value}")


@click.command(
    name="heroes",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Include developer fields (SAVE_REF, YAML).",
)
def heroes_cmd(verbose: bool) -> None:
    """List valid hero keys."""
    try:
        reg = registry.heroes()
    except RegistryError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    for index, hero in enumerate(reg.entries.values()):
        if index:
            click.echo()
        fields: list[tuple[str, object]] = [
            ("NAME", hero.display_name),
            ("KEY", hero.key),
        ]
        if verbose:
            fields.extend(
                [
                    ("SAVE_REF", hero.save_ref),
                    ("YAML", hero.yaml_path),
                ]
            )
        _echo_entry(fields)


@click.command(
    name="talents",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--for-hero",
    "hero_key",
    required=True,
    metavar="<str>",
    help="Hero key (e.g. geppetto). See `rerw game-assets inspect heroes`.",
)
@click.option(
    "-n",
    "--no-description",
    is_flag=True,
    default=False,
    help="Omit DESCRIPTION from output.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Include developer fields (GUID, CONTROLLER, IS_START, IS_ULT, ULT_UPGRADE_FOR).",
)
def talents_cmd(hero_key: str, no_description: bool, verbose: bool) -> None:
    """List valid talent keys for one hero."""
    try:
        reg = registry.hero_talents(hero_key)
    except RegistryError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    for index, talent in enumerate(reg.entries.values()):
        if index:
            click.echo()
        fields: list[tuple[str, object]] = [
            ("NAME", talent.display_name),
            ("KEY", talent.key),
        ]
        if not no_description:
            fields.append(("DESCRIPTION", talent.desc))
        if verbose:
            fields.extend(
                [
                    ("GUID", talent.guid.hex()),
                    ("CONTROLLER", talent.controller_name),
                    ("IS_START", str(talent.is_start).lower()),
                    ("IS_ULT", str(talent.is_ult).lower()),
                    ("ULT_UPGRADE_FOR", talent.ult_upgrade_for or ""),
                ]
            )
        _echo_entry(fields)


@click.command(
    name="items",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "-n",
    "--no-description",
    is_flag=True,
    default=False,
    help="Omit DESCRIPTION from output.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Include developer fields (GUID, EFFECT, RARITY).",
)
def items_cmd(no_description: bool, verbose: bool) -> None:
    """List valid magical-object keys."""
    try:
        reg = registry.magical_items()
    except RegistryError as exc:
        error(str(exc))
        raise SystemExit(1) from exc

    for index, item in enumerate(reg.entries.values()):
        if index:
            click.echo()
        fields: list[tuple[str, object]] = [
            ("NAME", item.display_name),
            ("KEY", item.key),
        ]
        if not no_description:
            fields.append(("DESCRIPTION", item.desc))
        if verbose:
            fields.extend(
                [
                    ("GUID", item.guid.hex()),
                    ("EFFECT", item.effect),
                    ("RARITY", item.rarity),
                ]
            )
        _echo_entry(fields)
