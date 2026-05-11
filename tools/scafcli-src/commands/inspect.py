"""scaffold inspect commands — read-only inspection of scaffold contents."""

from pathlib import Path

import click

from display_lib.output import info
from lib.manifest import load_manifest, resolve_modules, validate_manifest
from lib.paths import get_scaf_data_dir


def _resolve_data_path(manifest_path: str, scaf_data) -> Path:
    """Resolve manifest path to actual file path.

    Manifest paths like 'tools/scafcli-src/data/snippets/...' are resolved
    relative to the bundled data directory.
    """
    prefix = "tools/scafcli-src/data/"
    if manifest_path.startswith(prefix):
        return scaf_data / manifest_path[len(prefix) :]
    return scaf_data.parent.parent.parent / manifest_path


def _build_entries(manifest, modules, scaf_data):
    """Build ordered list of inspectable template entries."""
    entries = []

    # Static templates
    entries.append(
        {"label": ".gitignore", "path": scaf_data / "templates" / ".gitignore"}
    )
    entries.append(
        {
            "label": ".claude/settings.json",
            "path": scaf_data / "templates" / "settings.json",
        }
    )
    if "changelog" in modules:
        entries.append(
            {
                "label": "CHANGELOG.md",
                "content": (
                    "# Changelog\n\n"
                    "All notable changes to this project will be documented in this file.\n"
                ),
            }
        )

    # Assembled CLAUDE.md (all snippets joined)
    snippets = []
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        if "claude" in module["snippets"]:
            snippets.append(_resolve_data_path(module["snippets"]["claude"], scaf_data))

    if snippets:
        assembled = "\n\n".join(p.read_text().rstrip() for p in snippets) + "\n"
        entries.append(
            {
                "label": "CLAUDE.md",
                "suffix": "(assembled)",
                "content": assembled,
            }
        )

        # Individual snippets
        total = len(snippets)
        for i, path in enumerate(snippets, 1):
            entries.append(
                {
                    "label": f"CLAUDE.md \u2192 {path.name}",
                    "suffix": f"(snippet {i}/{total})",
                    "path": path,
                }
            )

    # Template entries from all modules
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for t in module.get("templates", []):
            if t["dest"].startswith("tools/"):
                continue
            src_path = _resolve_data_path(t["src"], scaf_data)
            if src_path.exists():
                entries.append({"label": t["dest"], "path": src_path})

    return entries


def _print_list(entries):
    for i, e in enumerate(entries, 1):
        suffix = e.get("suffix", "")
        line = f"  [{i}] {e['label']}"
        if suffix:
            line = f"{line:<40} {suffix}"
        info(line)


def _print_entry(entries, number):
    if number < 1 or number > len(entries):
        info(f"Invalid selection: {number}")
        return
    entry = entries[number - 1]
    info(f"\n\u2500\u2500\u2500 {entry['label']} \u2500\u2500\u2500")
    content = entry.get("content") or entry["path"].read_text()
    click.echo(content.rstrip())
    info("")


@click.command()
@click.argument("number", required=False, type=int)
@click.option("-N", "--non-interactive", is_flag=True, help="List templates and exit")
def templates_cmd(number, non_interactive):
    """List and view repo scaffold templates."""
    scaf_data = get_scaf_data_dir()

    manifest = load_manifest(scaf_data / "manifest.json")
    validate_manifest(manifest, scaf_data / "schemas" / "manifest.schema.json")
    modules = resolve_modules(manifest, include_github=True)
    entries = _build_entries(manifest, modules, scaf_data)

    if number is not None:
        _print_entry(entries, number)
        return

    _print_list(entries)

    if non_interactive:
        return

    while True:
        try:
            choice = click.prompt(
                f"\nSelect [1-{len(entries)}, q to quit]",
                default="q",
                show_default=False,
            )
        except click.Abort:
            break
        if choice.strip().lower() == "q":
            break
        try:
            _print_entry(entries, int(choice))
        except ValueError:
            info("Invalid selection")
