"""Tests for scaffold inspect templates command."""

from click.testing import CliRunner
from commands.inspect import _build_entries, templates_cmd
from lib.manifest import resolve_modules
from test_lib.cli import assert_cli_ok


class TestBuildEntries:
    def test_has_entries(self, manifest, scaf_data):
        modules = resolve_modules(manifest, include_github=True)
        entries = _build_entries(manifest, modules, scaf_data)
        # At minimum: .gitignore, settings.json, CHANGELOG.md, CLAUDE.md assembled, 2 snippets
        assert len(entries) >= 6

    def test_templates_then_assembled_then_snippets(self, manifest, scaf_data):
        modules = resolve_modules(manifest, include_github=True)
        entries = _build_entries(manifest, modules, scaf_data)
        # First 3 are templates
        assert entries[0]["label"] == ".gitignore"
        assert entries[1]["label"] == ".claude/settings.json"
        assert entries[2]["label"] == "CHANGELOG.md"
        # [3] is assembled CLAUDE.md
        assert entries[3]["label"] == "CLAUDE.md"
        assert entries[3].get("suffix") == "(assembled)"
        # [4]-[5] are individual snippets
        assert "\u2192" in entries[4]["label"]
        assert "\u2192" in entries[5]["label"]

    def test_assembled_contains_all_snippets(self, manifest, scaf_data):
        modules = resolve_modules(manifest, include_github=True)
        entries = _build_entries(manifest, modules, scaf_data)
        assembled = entries[3]["content"]
        assert "Commit Messages" in assembled
        assert "git-ai.sh" in assembled

    def test_snippets_have_suffix(self, manifest, scaf_data):
        modules = resolve_modules(manifest, include_github=True)
        entries = _build_entries(manifest, modules, scaf_data)
        assert entries[4].get("suffix") == "(snippet 1/2)"
        assert entries[5].get("suffix") == "(snippet 2/2)"

    def test_no_changelog_module_omits_changelog(self, manifest, scaf_data):
        modules = [
            m
            for m in resolve_modules(manifest, include_github=True)
            if m != "changelog"
        ]
        entries = _build_entries(manifest, modules, scaf_data)
        labels = [e["label"] for e in entries]
        assert "CHANGELOG.md" not in labels

    def test_all_entries_have_content_source(self, manifest, scaf_data):
        modules = resolve_modules(manifest, include_github=True)
        entries = _build_entries(manifest, modules, scaf_data)
        for entry in entries:
            assert entry.get("path") or entry.get("content"), (
                f"No content source for {entry['label']}"
            )

    def test_template_files_inspectable(self, manifest, scaf_data):
        """Non-tool template entries should appear as inspectable."""
        modules = resolve_modules(manifest, include_github=True)
        entries = _build_entries(manifest, modules, scaf_data)
        labels = [e["label"] for e in entries]
        # All non-tools/ template dests should be inspectable
        for mod_name in modules:
            module = manifest["modules"][mod_name]
            for t in module.get("templates", []):
                if not t["dest"].startswith("tools/"):
                    assert t["dest"] in labels, f"Template {t['dest']} not inspectable"

    def test_tool_content_not_in_selectable_entries(self, manifest, scaf_data):
        """Tool files and template_dirs should not appear as inspectable entries."""
        modules = resolve_modules(manifest, include_github=True)
        entries = _build_entries(manifest, modules, scaf_data)
        labels = [e["label"] for e in entries]
        # No tools/ prefix in inspectable labels
        for label in labels:
            assert not label.startswith("tools/"), f"Tool content leaked: {label}"


class TestTemplatesCommand:
    def test_direct_access_valid_number(self, manifest_path, schema_path):
        runner = CliRunner()
        result = runner.invoke(templates_cmd, ["1"])
        assert_cli_ok(result)
        assert ".gitignore" in result.output

    def test_direct_access_invalid_number(self, manifest_path, schema_path):
        runner = CliRunner()
        result = runner.invoke(templates_cmd, ["99"])
        assert_cli_ok(result)
        assert "Invalid selection" in result.output

    def test_interactive_mode_quit(self, manifest_path, schema_path):
        runner = CliRunner()
        result = runner.invoke(templates_cmd, [], input="q\n")
        assert_cli_ok(result)
        assert "[1]" in result.output

    def test_non_interactive_lists_and_exits(self, manifest_path, schema_path):
        runner = CliRunner()
        result = runner.invoke(templates_cmd, ["-N"])
        assert_cli_ok(result)
        assert "[1]" in result.output
        assert "Select" not in result.output
