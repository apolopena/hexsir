"""Tests for lib_scaf/assembler.py."""

import json

from lib.assembler import scaffold_to_dir
from lib.manifest import resolve_modules


class TestScaffoldToDir:
    def test_all_modules_creates_expected_files(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        report = scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        # Core assembled files
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / ".gitignore").exists()
        assert (tmp_path / ".claude" / "settings.json").exists()
        assert (tmp_path / "CHANGELOG.md").exists()

        # Planning files
        assert (tmp_path / ".claude" / "commands" / "generate-prp.md").exists()
        assert (tmp_path / ".claude" / "commands" / "execute-prp.md").exists()
        assert (tmp_path / ".ai" / "AGENTS.md").exists()

        # Priming files
        assert (tmp_path / ".claude" / "commands" / "prime-full.md").exists()
        assert (tmp_path / ".claude" / "agents" / "primer-generator.md").exists()

        # GitHub files
        assert (tmp_path / ".claude" / "agents" / "ghcli.md").exists()
        assert (tmp_path / ".github" / "workflows" / "gh-dispatch-ai.yml").exists()
        assert (tmp_path / "scripts" / "git-ai.sh").exists()

        # Changelog files
        assert (tmp_path / ".claude" / "agents" / "changelog-manager.md").exists()

        # Report
        assert "base" in report["modules_included"]
        assert len(report["files_created"]) > 0
        assert len(report["dirs_created"]) > 0

    def test_no_github_excludes_github_files(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=False)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        # GitHub files should NOT exist
        assert not (tmp_path / ".claude" / "agents" / "ghcli.md").exists()
        assert not (tmp_path / ".github").exists()
        assert not (tmp_path / "scripts" / "git-ai.sh").exists()

        # Base files should still exist
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / ".claude" / "settings.json").exists()

    def test_claude_md_has_base_directives(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        claude_md = (tmp_path / "CLAUDE.md").read_text()
        assert "Commit Messages" in claude_md
        assert "Planning System" in claude_md

    def test_claude_md_has_github_directives_when_included(
        self, manifest, source_repo, tmp_path
    ):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        claude_md = (tmp_path / "CLAUDE.md").read_text()
        assert "git-ai.sh" in claude_md
        assert "Mark agent" in claude_md

    def test_claude_md_lacks_github_directives_when_excluded(
        self, manifest, source_repo, tmp_path
    ):
        modules = resolve_modules(manifest, include_github=False)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        claude_md = (tmp_path / "CLAUDE.md").read_text()
        assert "Commit Messages" in claude_md  # base present
        assert "git-ai.sh" not in claude_md  # github absent
        assert "Mark agent" not in claude_md  # github absent

    def test_settings_json_valid(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "permissions" in settings
        assert "allow" in settings["permissions"]

    def test_required_dirs_created(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        assert (tmp_path / ".ai" / "scratch").is_dir()
        assert (tmp_path / ".ai" / "planning" / "prp" / "instances").is_dir()
        assert (tmp_path / ".ai" / "planning" / "prp" / "proposals").is_dir()
        assert (tmp_path / ".github" / "workflows").is_dir()
        assert (tmp_path / "scripts").is_dir()

    def test_changelog_template(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        changelog = (tmp_path / "CHANGELOG.md").read_text()
        assert "# Changelog" in changelog
        assert "All notable changes" in changelog

    def test_git_ai_executable(self, manifest, source_repo, tmp_path):
        """git-ai.sh should preserve executable permission."""
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        import os

        git_ai = tmp_path / "scripts" / "git-ai.sh"
        assert os.access(git_ai, os.X_OK)
