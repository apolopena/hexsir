"""Tree rendering — core renderer and path-based convenience."""

from display_lib.output import DIM, NC

from .types import StaticEntry, StaticTreeResult, TreeNode


def render_tree(
    root: TreeNode,
    root_connectors: bool = False,
    dim_connectors: bool = False,
) -> StaticTreeResult:
    """Render a TreeNode hierarchy into lines.

    Takes an explicit tree you built yourself. Each TreeNode has text,
    optional children, optional label, and optional color. The root
    node's text is not rendered — only its children are. This lets you
    use the root as a logical container without it appearing in output.

    Args:
        root: The root TreeNode. Its children are the top-level entries.
        root_connectors: If True, top-level entries get connectors (├─/└─).
            If False (default), top-level entries render plain.
        dim_connectors: If True, connectors render in dim.

    Returns:
        StaticTreeResult with lines. May contain ANSI codes if nodes
        have color set or dim_connectors is True.
    """
    lines: list[str] = []
    _render_nodes(root.children, lines, "", root_connectors, dim_connectors)
    return StaticTreeResult(lines=lines)


def render_tree_from_paths(
    entries: list[StaticEntry],
    root_connectors: bool = False,
    dim_connectors: bool = False,
) -> StaticTreeResult:
    """Build a tree from slash-delimited paths, then render it.

    Convenience wrapper around render_tree(). Takes a flat list of
    slash-delimited path strings, builds the TreeNode hierarchy by
    splitting on '/' and grouping shared segments, then renders.

    Use this when your data is naturally path-shaped (file trees,
    dependency hierarchies, CLI subcommand trees). Use render_tree()
    directly when you need arbitrary text in nodes or explicit control
    over the hierarchy.

    Validation (returns error via StaticTreeResult.error):
        - No duplicate paths
        - label_position in range of segment count when provided
        - label_position requires label to be set

    Args:
        entries: List of StaticEntry, each with a slash-delimited path.
        root_connectors: If True, top-level entries get connectors.
        dim_connectors: If True, connectors render in dim.

    Returns:
        StaticTreeResult with plain-text lines.
    """
    # Validate
    seen_paths = set()
    for entry in entries:
        if entry.path in seen_paths:
            return StaticTreeResult(error=f"Duplicate path: {entry.path}")
        seen_paths.add(entry.path)

        if entry.label_position is not None:
            if entry.label is None:
                return StaticTreeResult(
                    error=f"label_position requires label: {entry.path}"
                )
            segment_count = len(entry.path.split("/"))
            if entry.label_position < 0 or entry.label_position >= segment_count:
                return StaticTreeResult(
                    error=f"label_position {entry.label_position} out of range "
                    f"for {segment_count} segments: {entry.path}"
                )

    # Build TreeNode hierarchy from paths
    root = TreeNode(text="")

    for entry in entries:
        parts = entry.path.split("/")
        current = root
        for part in parts:
            existing = None
            for child in current.children:
                if child.text == part:
                    existing = child
                    break
            if existing is None:
                existing = TreeNode(text=part)
                current.children.append(existing)
            current = existing

        if entry.label is not None:
            if entry.label_position is not None:
                target = root
                for part in parts[: entry.label_position + 1]:
                    for child in target.children:
                        if child.text == part:
                            target = child
                            break
                target.label = entry.label
            else:
                current.label = entry.label

    # Path-specific: sort directories before files, add / suffix
    _prepare_path_nodes(root)

    # Render
    lines: list[str] = []
    _render_nodes(root.children, lines, "", root_connectors, dim_connectors)
    return StaticTreeResult(lines=lines)


def _prepare_path_nodes(node: TreeNode) -> None:
    """Sort children (dirs before files, alpha) and add / suffix to dirs.

    This is path-specific preparation — only called by render_tree_from_paths.
    """
    if not node.children:
        return

    node.children.sort(key=lambda n: (len(n.children) == 0, n.text))

    for child in node.children:
        if child.children and not child.text.endswith("/"):
            child.text += "/"
        _prepare_path_nodes(child)


def _render_nodes(
    nodes: list[TreeNode],
    lines: list[str],
    prefix: str,
    use_connectors: bool,
    dim_connectors: bool,
) -> None:
    """Recursively render nodes into lines.

    This is the core renderer. It is dumb — it preserves insertion order,
    applies node color if set, and renders connectors. It makes no decisions
    about sorting, suffixes, or styling beyond what the nodes specify.
    """
    for i, node in enumerate(nodes):
        is_last = i == len(nodes) - 1
        suffix = f" [{node.label}]" if node.label else ""
        text = f"{node.color}{node.text}{NC}" if node.color else node.text

        if use_connectors:
            connector = "└─ " if is_last else "├─ "
            if dim_connectors:
                connector = f"{DIM}{connector}{NC}"
            lines.append(f"{prefix}{connector}{text}{suffix}")
            if node.children:
                if dim_connectors:
                    extension = "   " if is_last else f"{DIM}│{NC}  "
                else:
                    extension = "   " if is_last else "│  "
                _render_nodes(
                    node.children, lines, prefix + extension, True, dim_connectors
                )
        else:
            lines.append(f"{prefix}{text}{suffix}")
            if node.children:
                _render_nodes(node.children, lines, prefix, True, dim_connectors)
