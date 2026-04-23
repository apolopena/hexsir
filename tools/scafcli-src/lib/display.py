"""Display utilities for scaffold CLI."""

from pathlib import Path

from display_lib.output import info
from tree_lib import StaticEntry, render_tree_from_paths


_DIR_EXCLUDE = {".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", "build"}
_DIR_EXCLUDE_SUFFIXES = {".egg-info"}
_DIR_EXCLUDE_FILES = {".coverage"}


def print_file_tree(manifest: dict, modules: list[str], source_repo: Path) -> None:
    """Print the full output file tree from manifest content."""
    paths = set()

    for mod_name in modules:
        module = manifest["modules"][mod_name]

        # Scaffolded files (verbatim copies)
        for file_entry in module.get("files", []):
            paths.add(file_entry["dest"])

        # Template entries (trimmed for scaffolded repos)
        for file_entry in module.get("templates", []):
            paths.add(file_entry["dest"])

        # Scaffolded trees (verbatim directory copies)
        for td in module.get("template_dirs", []):
            src_dir = source_repo / td["src"]
            if src_dir.is_dir():
                for file_path in src_dir.rglob("*"):
                    if file_path.is_file():
                        parts = file_path.relative_to(src_dir).parts
                        if _DIR_EXCLUDE & set(parts):
                            continue
                        if any(
                            p.endswith(s) for p in parts for s in _DIR_EXCLUDE_SUFFIXES
                        ):
                            continue
                        if file_path.name in _DIR_EXCLUDE_FILES:
                            continue
                        relative = file_path.relative_to(src_dir)
                        paths.add(f"{td['dest']}/{relative}")

    # Assembled files
    paths.add("CLAUDE.md")
    paths.add(".gitignore")
    if "changelog" in modules:
        paths.add("CHANGELOG.md")

    entries = [StaticEntry(p) for p in sorted(paths)]
    result = render_tree_from_paths(entries)
    if result.error:
        info(f"(tree error: {result.error})")
        return
    for line in result.lines:
        info(line)
