"""Type definitions for tree-lib."""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class TreeNode:
    """A node in a tree for explicit hierarchy construction.

    text: Display text for this node.
    children: Child nodes (empty list = leaf).
    label: Optional annotation appended as [label].
    color: ANSI code(s) — e.g. GREEN, f"{BOLD}{YELLOW}".
           Always pair BOLD with a color. Children do not inherit.
    """

    text: str
    children: list["TreeNode"] = field(default_factory=list)
    label: str | None = None
    color: str | None = None


@dataclass
class StaticEntry:
    """One entry for a static tree.

    Each entry defines a path in the hierarchy (slash-delimited) with an
    optional label. A single entry may produce multiple nodes in the
    rendered tree — one per path segment.
    """

    path: str
    label: str | None = None
    label_position: int | None = None


@dataclass
class StaticTreeResult:
    """Result of a static tree render.

    Exactly one of lines/error will be set. Caller must check error
    before using lines.
    """

    lines: list[str] | None = None
    error: str | None = None


@dataclass
class TaskEntry:
    """One task for a dynamic tree.

    Describes a single operation to execute with tree-formatted
    pass/fail reporting.
    """

    label: str
    action: Callable
    spin: bool = False
    done_label: str | None = None
    on_fail: Callable | None = None
    exit_code: int = 1
    is_last: bool = False
    indent: str = ""
