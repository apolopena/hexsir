"""Tests for tree rendering — render_tree and render_tree_from_paths."""

from display_lib.output import GREEN, NC

from tree_lib import StaticEntry, TreeNode, render_tree, render_tree_from_paths


class TestRenderTreeFromPaths:
    """Tests for path-based tree rendering."""

    def test_plain_tree(self):
        """Plain tree with nested paths renders correctly."""
        entries = [
            StaticEntry("a/b"),
            StaticEntry("a/c"),
            StaticEntry("d"),
        ]
        result = render_tree_from_paths(entries)
        assert result.error is None
        assert result.lines == [
            "a/",
            "├─ b",
            "└─ c",
            "d",
        ]

    def test_labeled_tree(self):
        """Labels appended as [label] to leaf."""
        entries = [StaticEntry("x", label="new")]
        result = render_tree_from_paths(entries)
        assert result.error is None
        assert result.lines == ["x [new]"]

    def test_label_position_middle_node(self):
        """label_position places label on a non-leaf segment."""
        entries = [
            StaticEntry("requests/urllib3/ssl", label="2.1.0", label_position=1),
        ]
        result = render_tree_from_paths(entries)
        assert result.error is None
        assert any("[2.1.0]" in line and "urllib3" in line for line in result.lines)
        assert not any("[2.1.0]" in line and "ssl" in line for line in result.lines)

    def test_duplicate_path_error(self):
        """Duplicate paths return error."""
        entries = [StaticEntry("a/b"), StaticEntry("a/b")]
        result = render_tree_from_paths(entries)
        assert result.error is not None
        assert "Duplicate path" in result.error

    def test_label_position_out_of_range(self):
        """label_position out of range returns error."""
        entries = [StaticEntry("a/b", label="v1", label_position=5)]
        result = render_tree_from_paths(entries)
        assert result.error is not None
        assert "out of range" in result.error

    def test_label_position_without_label(self):
        """label_position without label returns error."""
        entries = [StaticEntry("a/b", label_position=0)]
        result = render_tree_from_paths(entries)
        assert result.error is not None
        assert "label_position requires label" in result.error

    def test_root_connectors_false(self):
        """Default: top-level entries render plain, children get connectors."""
        entries = [
            StaticEntry("src/main.py"),
            StaticEntry("README.md"),
        ]
        result = render_tree_from_paths(entries, root_connectors=False)
        assert result.error is None
        assert result.lines[0] == "src/"
        assert "└─ main.py" in result.lines[1]
        assert result.lines[2] == "README.md"

    def test_root_connectors_true(self):
        """root_connectors=True: all entries get connectors."""
        entries = [
            StaticEntry("src/main.py"),
            StaticEntry("README.md"),
        ]
        result = render_tree_from_paths(entries, root_connectors=True)
        assert result.error is None
        assert "├─ src/" in result.lines[0]
        assert "└─ README.md" in result.lines[-1]

    def test_directories_sort_before_files(self):
        """Directories (nodes with children) sort before leaf nodes."""
        entries = [
            StaticEntry("b_file"),
            StaticEntry("a_dir/child"),
        ]
        result = render_tree_from_paths(entries)
        assert result.error is None
        assert result.lines[0] == "a_dir/"
        assert "child" in result.lines[1]
        assert "b_file" in result.lines[2]

    def test_empty_entries(self):
        """Empty entries list returns empty lines."""
        result = render_tree_from_paths([])
        assert result.error is None
        assert result.lines == []

    def test_directory_suffix(self):
        """Nodes with children get / suffix."""
        entries = [StaticEntry("foo/bar")]
        result = render_tree_from_paths(entries)
        assert result.error is None
        assert result.lines[0] == "foo/"


class TestRenderTree:
    """Tests for explicit node-based tree rendering."""

    def test_simple_tree(self):
        """Flat list of children renders with connectors."""
        root = TreeNode(
            "",
            children=[
                TreeNode("first"),
                TreeNode("second"),
                TreeNode("third"),
            ],
        )
        result = render_tree(root, root_connectors=True)
        assert result.error is None
        assert "├─ first" in result.lines[0]
        assert "├─ second" in result.lines[1]
        assert "└─ third" in result.lines[2]

    def test_nested_tree(self):
        """Nested children render with proper indentation."""
        root = TreeNode(
            "",
            children=[
                TreeNode(
                    "parent",
                    children=[
                        TreeNode("child"),
                    ],
                ),
            ],
        )
        result = render_tree(root, root_connectors=True)
        assert result.error is None
        assert len(result.lines) == 2
        assert "parent" in result.lines[0]
        assert "child" in result.lines[1]

    def test_preserves_insertion_order(self):
        """Unlike path-based, node-based preserves insertion order."""
        root = TreeNode(
            "",
            children=[
                TreeNode("zebra"),
                TreeNode("alpha"),
                TreeNode("middle"),
            ],
        )
        result = render_tree(root, root_connectors=True)
        assert "zebra" in result.lines[0]
        assert "alpha" in result.lines[1]
        assert "middle" in result.lines[2]

    def test_no_directory_suffix(self):
        """Node-based trees don't add / to parents."""
        root = TreeNode(
            "",
            children=[
                TreeNode(
                    "Directly:",
                    children=[
                        TreeNode("some command"),
                    ],
                ),
            ],
        )
        result = render_tree(root, root_connectors=True)
        assert "Directly:" in result.lines[0]
        assert "Directly:/" not in result.lines[0]

    def test_label_on_node(self):
        """Labels appended as [label]."""
        root = TreeNode(
            "",
            children=[
                TreeNode("item", label="new"),
            ],
        )
        result = render_tree(root, root_connectors=True)
        assert "[new]" in result.lines[0]

    def test_color_on_node(self):
        """Color applied to node text."""
        root = TreeNode(
            "",
            children=[
                TreeNode("colored", color=GREEN),
            ],
        )
        result = render_tree(root, root_connectors=True)
        assert GREEN in result.lines[0]
        assert NC in result.lines[0]

    def test_no_color_no_ansi(self):
        """Nodes without color produce no ANSI codes in text."""
        root = TreeNode(
            "",
            children=[
                TreeNode("plain"),
            ],
        )
        result = render_tree(root, root_connectors=True)
        assert "\033[" not in result.lines[0].replace("└─ ", "")

    def test_dim_connectors(self):
        """dim_connectors wraps connectors in DIM."""
        from display_lib.output import DIM

        root = TreeNode(
            "",
            children=[
                TreeNode("item"),
            ],
        )
        result = render_tree(root, root_connectors=True, dim_connectors=True)
        assert DIM in result.lines[0]

    def test_root_text_not_rendered(self):
        """Root node's text does not appear in output."""
        root = TreeNode(
            "invisible root",
            children=[
                TreeNode("visible child"),
            ],
        )
        result = render_tree(root, root_connectors=True)
        assert all("invisible root" not in line for line in result.lines)
        assert any("visible child" in line for line in result.lines)

    def test_root_connectors_false(self):
        """Without root connectors, top-level items have no connector."""
        root = TreeNode(
            "",
            children=[
                TreeNode("top level"),
            ],
        )
        result = render_tree(root, root_connectors=False)
        assert result.lines[0] == "top level"

    def test_slashes_in_text_not_split(self):
        """Slashes in node text are literal, not hierarchy separators."""
        root = TreeNode(
            "",
            children=[
                TreeNode("./tools/adcli session-info 110"),
            ],
        )
        result = render_tree(root, root_connectors=True)
        assert len(result.lines) == 1
        assert "./tools/adcli session-info 110" in result.lines[0]
