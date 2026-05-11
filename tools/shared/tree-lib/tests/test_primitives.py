"""Tests for tree rendering primitives (migrated from display-lib)."""

from display_lib.output import BRIGHT_GREEN, GREEN, RED, YELLOW

from tree_lib import (
    TREE_INDENT_PIPE,
    TREE_INDENT_SPACE,
    tree_fail,
    tree_group,
    tree_item,
    tree_ok,
    tree_warn,
)


class TestTreeHelpers:
    """Tests for logical tree output helpers."""

    def test_tree_group_prints_green(self, capsys):
        """tree_group() prints green label."""
        tree_group("Schema")
        captured = capsys.readouterr()
        assert GREEN in captured.out
        assert "Schema" in captured.out

    def test_tree_group_with_indent(self, capsys):
        """tree_group() respects indent parameter."""
        tree_group("Schema", indent="  ")
        captured = capsys.readouterr()
        assert captured.out.startswith("  ")

    def test_tree_ok_prints_checkmark(self, capsys):
        """tree_ok() prints green checkmark with connector."""
        tree_ok("ids unique")
        captured = capsys.readouterr()
        assert "✓" in captured.out
        assert BRIGHT_GREEN in captured.out
        assert "ids unique" in captured.out
        assert "├─" in captured.out  # mid connector

    def test_tree_ok_last_uses_end_connector(self, capsys):
        """tree_ok(is_last=True) uses └─ connector."""
        tree_ok("all passed", is_last=True)
        captured = capsys.readouterr()
        assert "└─" in captured.out

    def test_tree_ok_with_indent(self, capsys):
        """tree_ok() respects indent parameter."""
        tree_ok("valid", indent="  ")
        captured = capsys.readouterr()
        assert captured.out.startswith("  ")

    def test_tree_fail_prints_cross_to_stderr(self, capsys):
        """tree_fail() prints red cross to stderr."""
        tree_fail("missing file")
        captured = capsys.readouterr()
        assert "✗" in captured.err
        assert RED in captured.err
        assert "missing file" in captured.err
        assert captured.out == ""

    def test_tree_fail_last_uses_end_connector(self, capsys):
        """tree_fail(is_last=True) uses └─ connector."""
        tree_fail("broken", is_last=True)
        captured = capsys.readouterr()
        assert "└─" in captured.err

    def test_tree_item_neutral_no_symbol(self, capsys):
        """tree_item() prints connector without status symbol."""
        tree_item("data/internals.json")
        captured = capsys.readouterr()
        assert "├─" in captured.out
        assert "data/internals.json" in captured.out
        assert "✓" not in captured.out
        assert "✗" not in captured.out

    def test_tree_item_last(self, capsys):
        """tree_item(is_last=True) uses └─ connector."""
        tree_item("last entry", is_last=True)
        captured = capsys.readouterr()
        assert "└─" in captured.out

    def test_tree_warn_prints_warning(self, capsys):
        """tree_warn() prints yellow warning symbol."""
        tree_warn("partial failure")
        captured = capsys.readouterr()
        assert "⚠" in captured.out
        assert YELLOW in captured.out
        assert "partial failure" in captured.out
        assert "├─" in captured.out

    def test_tree_warn_last(self, capsys):
        """tree_warn(is_last=True) uses └─ connector."""
        tree_warn("done with errors", is_last=True)
        captured = capsys.readouterr()
        assert "└─" in captured.out

    def test_tree_indent_constants(self):
        """Indent constants have correct box-drawing chars."""
        assert "│" in TREE_INDENT_PIPE
        assert len(TREE_INDENT_SPACE) == len(TREE_INDENT_PIPE)
