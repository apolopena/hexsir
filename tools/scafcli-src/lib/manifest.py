"""Manifest loading, validation, and module resolution."""

import json
from pathlib import Path

import jsonschema

from lib.errors import schema_error

# Canonical module order
MODULE_ORDER = [
    "base",
    "planning",
    "priming",
    "github",
    "changelog",
    "scripts",
    "documentation",
    "tooling",
    "backend-lib",
]


def load_manifest(manifest_path: Path) -> dict:
    """Load manifest JSON. Exits on parse failure."""
    try:
        with open(manifest_path) as f:
            return json.load(f)
    except FileNotFoundError:
        schema_error(f"Manifest not found: {manifest_path}")
    except json.JSONDecodeError as e:
        schema_error(f"Manifest is not valid JSON: {e}")


def validate_manifest(manifest: dict, schema_path: Path) -> None:
    """Validate manifest against JSON Schema. Exits on failure."""
    try:
        with open(schema_path) as f:
            schema = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        schema_error(f"Cannot load schema: {e}")

    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as e:
        schema_error(f"Manifest schema invalid: {e.message}")


def resolve_modules(
    manifest: dict,
    include_github: bool = True,
    include_backend_lib: bool = True,
) -> list[str]:
    """Return ordered list of module names to include.

    Args:
        manifest: Loaded manifest dict.
        include_github: If False, exclude github module.
        include_backend_lib: If False, exclude backend-lib module.
    """
    modules = []
    for name in MODULE_ORDER:
        if name in manifest["modules"]:
            if name == "github" and not include_github:
                continue
            if name == "backend-lib" and not include_backend_lib:
                continue
            modules.append(name)
    return modules


def check_source_files(
    manifest: dict, modules: list[str], source_repo: Path
) -> list[str]:
    """Return list of missing source files for selected modules."""
    missing = []

    for mod_name in modules:
        module = manifest["modules"][mod_name]

        # Check file sources
        for file_entry in module.get("files", []):
            src_path = source_repo / file_entry["src"]
            if not src_path.exists():
                missing.append(file_entry["src"])

        # Check template sources
        for file_entry in module.get("templates", []):
            src_path = source_repo / file_entry["src"]
            if not src_path.exists():
                missing.append(file_entry["src"])

        # Check scaffolded-tree sources
        for td in module.get("template_dirs", []):
            src_dir = source_repo / td["src"]
            if not src_dir.is_dir():
                missing.append(td["src"])

        # Check snippet sources
        for snippet_path in module["snippets"].values():
            if not (source_repo / snippet_path).exists():
                missing.append(snippet_path)

    # Check template files
    gitignore_path = (
        source_repo / "tools" / "scafcli-src" / "data" / "templates" / ".gitignore"
    )
    if not gitignore_path.exists():
        missing.append("tools/scafcli-src/data/templates/.gitignore")

    return missing
