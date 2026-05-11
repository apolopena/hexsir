"""Post-scaffold validation."""

import json
from pathlib import Path

from display_lib.output import error, success


def validate_scaffold(
    manifest: dict, modules: list[str], target_dir: Path
) -> list[tuple[str, bool, str]]:
    """Validate scaffolded output. Returns list of (check, passed, message)."""
    results = []

    # Check every file from selected modules exists in target
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for file_entry in module.get("files", []):
            dest = target_dir / file_entry["dest"]
            passed = dest.exists()
            results.append(("file_exists", passed, file_entry["dest"]))

    # Check template files exist in target
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for file_entry in module.get("templates", []):
            dest = target_dir / file_entry["dest"]
            passed = dest.exists()
            results.append(("template_exists", passed, file_entry["dest"]))

    # Check template directories exist and are non-empty
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for td in module.get("template_dirs", []):
            dest_dir = target_dir / td["dest"]
            if dest_dir.is_dir() and any(dest_dir.rglob("*")):
                results.append(("template_dir_exists", True, f"{td['dest']}/"))
            else:
                results.append(
                    ("template_dir_exists", False, f"{td['dest']}/ missing or empty")
                )

    # Check all required directories exist
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for dir_path in module["dirs"]:
            full_path = target_dir / dir_path
            passed = full_path.is_dir()
            results.append(("dir_exists", passed, dir_path))

    # Check .claude/settings.json is valid JSON
    settings_path = target_dir / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            with open(settings_path) as f:
                json.load(f)
            results.append(("settings_json_valid", True, ".claude/settings.json"))
        except (json.JSONDecodeError, OSError) as e:
            results.append(
                ("settings_json_valid", False, f".claude/settings.json: {e}")
            )
    else:
        results.append(
            ("settings_json_valid", False, ".claude/settings.json not found")
        )

    # Check CLAUDE.md exists and is non-empty
    claude_md = target_dir / "CLAUDE.md"
    if claude_md.exists() and claude_md.stat().st_size > 0:
        results.append(("claude_md", True, "CLAUDE.md"))
    else:
        results.append(("claude_md", False, "CLAUDE.md missing or empty"))

    # Check .gitignore exists and is non-empty
    gitignore = target_dir / ".gitignore"
    if gitignore.exists() and gitignore.stat().st_size > 0:
        results.append(("gitignore", True, ".gitignore"))
    else:
        results.append(("gitignore", False, ".gitignore missing or empty"))

    return results


def print_validation(results: list[tuple[str, bool, str]]) -> bool:
    """Print validation results. Returns True if all passed."""
    all_passed = True
    for _check, passed, msg in results:
        if passed:
            success(msg)
        else:
            error(msg)
            all_passed = False
    return all_passed
