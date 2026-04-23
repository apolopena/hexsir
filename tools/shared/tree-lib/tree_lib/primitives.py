"""Tree rendering primitives — status output helpers."""

import sys

from display_lib.output import GREEN, NC, YELLOW, format_fail, format_ok

TREE_INDENT_PIPE = "│  "
TREE_INDENT_SPACE = "   "


def tree_group(label: str, indent: str = "") -> None:
    """Print a tree group header."""
    print(f"{indent}{GREEN}{label}{NC}")


def tree_ok(message: str, is_last: bool = False, indent: str = "") -> None:
    """Print a tree item with success indicator."""
    connector = "└─" if is_last else "├─"
    print(f"{indent}{connector} {format_ok(message)}")


def tree_fail(message: str, is_last: bool = False, indent: str = "") -> None:
    """Print a tree item with failure indicator."""
    connector = "└─" if is_last else "├─"
    print(f"{indent}{connector} {format_fail(message)}", file=sys.stderr)


def tree_warn(message: str, is_last: bool = False, indent: str = "") -> None:
    """Print a tree item with warning indicator."""
    connector = "└─" if is_last else "├─"
    print(f"{indent}{connector} {YELLOW}⚠ {message}{NC}")


def tree_item(message: str, is_last: bool = False, indent: str = "") -> None:
    """Print a neutral tree item (no status indicator)."""
    connector = "└─ " if is_last else "├─ "
    print(f"{indent}{connector}{message}")
