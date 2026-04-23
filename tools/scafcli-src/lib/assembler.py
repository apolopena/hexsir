"""File assembly and scaffolding operations."""

import shutil
from pathlib import Path

from display_lib.output import info
from tree_lib import StaticEntry, render_tree_from_paths


def scaffold_to_dir(
    manifest: dict, modules: list[str], source_repo: Path, target_dir: Path
) -> dict:
    """Scaffold all selected modules into target_dir.

    Returns report dict with files_created, dirs_created, modules_included,
    templates_created, template_dirs_created.
    """
    report = {
        "files_created": [],
        "dirs_created": [],
        "modules_included": list(modules),
        "templates_created": [],
        "template_dirs_created": [],
    }

    # Create required directories from all selected modules
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        created = _create_module_dirs(module, target_dir)
        report["dirs_created"].extend(created)

    # Copy files from all selected modules (repo files + templates)
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        created = _copy_file_entries(module.get("files", []), source_repo, target_dir)
        report["files_created"].extend(created)
        created = _copy_file_entries(
            module.get("templates", []), source_repo, target_dir
        )
        report["templates_created"].extend(created)

    # Copy template directories
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for td in module.get("template_dirs", []):
            src_dir = source_repo / td["src"]
            dest_dir = target_dir / td["dest"]
            file_count = _copy_tree(src_dir, dest_dir)
            report["template_dirs_created"].append(
                {"dest": td["dest"], "file_count": file_count}
            )

    # Assemble CLAUDE.md from snippets
    _assemble_claude_md(manifest, modules, source_repo, target_dir)
    report["templates_created"].append("CLAUDE.md")

    # Copy .gitignore
    gitignore_src = (
        source_repo / "tools" / "scafcli-src" / "data" / "templates" / ".gitignore"
    )
    gitignore_dest = target_dir / ".gitignore"
    shutil.copy2(gitignore_src, gitignore_dest)
    report["templates_created"].append(".gitignore")

    # Create empty CHANGELOG.md if changelog module selected
    if "changelog" in modules:
        changelog_path = target_dir / "CHANGELOG.md"
        changelog_path.write_text(
            "# Changelog\n\n"
            "All notable changes to this project will be documented in this file.\n"
        )
        report["templates_created"].append("CHANGELOG.md")

    # Set executable bits on scripts and bash wrappers
    _set_executable_bits(target_dir)

    return report


def _copy_file_entries(
    entries: list[dict], source_repo: Path, target_dir: Path
) -> list[str]:
    """Copy src→dest file entries. Returns list of dest paths created."""
    created = []
    for file_entry in entries:
        src = source_repo / file_entry["src"]
        dest = target_dir / file_entry["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        created.append(file_entry["dest"])
    return created


def _create_module_dirs(module: dict, target_dir: Path) -> list[str]:
    """Create all required directories for a module. Returns list created."""
    created = []
    for dir_path in module["dirs"]:
        full_path = target_dir / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        created.append(dir_path)
    return created


_DIR_EXCLUDE = {".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", "build"}
_DIR_EXCLUDE_SUFFIXES = {".egg-info"}
_DIR_EXCLUDE_FILES = {".coverage"}


def _is_excluded(parts, filename):
    """Check if a file path should be excluded from copy/display operations."""
    if _DIR_EXCLUDE & set(parts):
        return True
    if any(p.endswith(s) for p in parts for s in _DIR_EXCLUDE_SUFFIXES):
        return True
    if filename in _DIR_EXCLUDE_FILES:
        return True
    return False


def _walk_for_display(directory: Path) -> list[str]:
    """Collect file paths from a directory for tree display, excluding artifacts."""
    paths = []
    for f in sorted(directory.rglob("*")):
        if not f.is_file():
            continue
        parts = f.relative_to(directory).parts
        if _is_excluded(parts, f.name):
            continue
        paths.append(str(f.relative_to(directory)))
    return paths


def _copy_tree(src_dir: Path, dest_dir: Path) -> int:
    """Recursively copy a source tree into dest. Returns file count.
    Excludes artifact directories (.venv, __pycache__, build, .egg-info, etc.)."""
    file_count = 0
    for src_file in sorted(src_dir.rglob("*")):
        if src_file.is_file():
            parts = src_file.relative_to(src_dir).parts
            if _is_excluded(parts, src_file.name):
                continue
            relative = src_file.relative_to(src_dir)
            dest_file = dest_dir / relative
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            file_count += 1
    return file_count


def _set_executable_bits(target_dir: Path) -> None:
    """Set executable bits on scripts and bash wrappers."""
    scripts_dir = target_dir / "scripts"
    if scripts_dir.exists():
        for script in scripts_dir.glob("*.sh"):
            script.chmod(script.stat().st_mode | 0o755)

    # Bash wrappers in tools/ (no extension)
    tools_dir = target_dir / "tools"
    if tools_dir.exists():
        for item in tools_dir.iterdir():
            if item.is_file() and not item.suffix:
                item.chmod(item.stat().st_mode | 0o755)


def _assemble_claude_md(
    manifest: dict, modules: list[str], source_repo: Path, target_dir: Path
) -> None:
    """Assemble CLAUDE.md from snippet files of selected modules."""
    snippets = []
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        if "claude" in module["snippets"]:
            snippet_path = source_repo / module["snippets"]["claude"]
            snippets.append(snippet_path.read_text().rstrip())

    claude_md = "\n\n".join(snippets) + "\n"
    (target_dir / "CLAUDE.md").write_text(claude_md)


def print_report(report: dict) -> None:
    """Print scaffold report."""
    info(f"Modules: {', '.join(report['modules_included'])}")
    info(f"Files: {len(report['files_created'])}")
    info(f"Templates: {len(report['templates_created'])}")
    info(f"Directories: {len(report['dirs_created'])}")

    for td in report.get("template_dirs_created", []):
        info(f"  {td['dest']}/ ({td['file_count']} files)")


def print_dry_run(manifest: dict, modules: list[str], source_repo: Path) -> None:
    """Print what would be created without creating."""
    info("[dry-run] Modules to include:")
    for mod in modules:
        info(f"  - {mod}")

    info("\n[dry-run] Files to copy:")
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for f in module.get("files", []):
            info(f"  {f['src']} -> {f['dest']}")

    info("\n[dry-run] Directories to create:")
    seen_dirs = set()
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for d in module["dirs"]:
            if d not in seen_dirs:
                info(f"  {d}")
                seen_dirs.add(d)

    # Count snippets for CLAUDE.md label
    snippet_count = sum(
        1
        for mod_name in modules
        if "claude" in manifest["modules"][mod_name]["snippets"]
    )

    info("\n[dry-run] Templated:")
    info(f"  CLAUDE.md (assembled from {snippet_count} snippets)")
    info("  .gitignore")
    if "changelog" in modules:
        info("  CHANGELOG.md")

    # Template entries
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for t in module.get("templates", []):
            info(f"  {t['dest']}")

    # Scaffolded trees (verbatim directory copies)
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for td in module.get("template_dirs", []):
            src_dir = source_repo / td["src"]
            info(f"  {td['dest']}/")
            paths = _walk_for_display(src_dir)
            entries = [StaticEntry(p) for p in paths]
            result = render_tree_from_paths(entries, root_connectors=True)
            if result.lines:
                for line in result.lines:
                    info(f"    {line}")
