"""Error categories, exit codes, and formatted output for scafcli."""

import sys

from display_lib.output import error as color_error

# Exit codes by category
EXIT_SCHEMA = 1  # Manifest/schema validation failed
EXIT_REFERENCE = 2  # Missing source file, bad module reference
EXIT_ENVIRONMENT = 3  # Missing tool (git, gh), auth failure, network
EXIT_RUNTIME = 4  # Scaffold operation failed (copy, tarball, git)
EXIT_CONFLICT = 5  # File conflicts in existing repo (without --force)


def schema_error(msg: str) -> None:
    """Print schema error and exit."""
    color_error(f"[schema] {msg}")
    sys.exit(EXIT_SCHEMA)


def ref_error(msg: str) -> None:
    """Print reference error and exit."""
    color_error(f"[reference] {msg}")
    sys.exit(EXIT_REFERENCE)


def env_error(msg: str) -> None:
    """Print environment error and exit."""
    color_error(f"[environment] {msg}")
    sys.exit(EXIT_ENVIRONMENT)


def runtime_error(msg: str) -> None:
    """Print runtime error and exit."""
    color_error(f"[runtime] {msg}")
    sys.exit(EXIT_RUNTIME)


def conflict_error(msg: str) -> None:
    """Print conflict error and exit."""
    color_error(f"[conflict] {msg}")
    sys.exit(EXIT_CONFLICT)
