"""Tests for lib_scaf/validator.py."""

from lib.assembler import scaffold_to_dir
from lib.manifest import resolve_modules
from lib.validator import validate_scaffold


class TestValidateScaffold:
    def test_valid_scaffold_all_pass(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        results = validate_scaffold(manifest, modules, tmp_path)
        failures = [(check, msg) for check, passed, msg in results if not passed]
        assert failures == [], f"Validation failures: {failures}"

    def test_missing_file_detected(self, tmp_path):
        manifest = {
            "modules": {
                "test": {
                    "files": [{"src": "x.txt", "dest": "missing.txt"}],
                    "dirs": [],
                    "snippets": {},
                }
            }
        }
        # Create minimal required files for other checks
        (tmp_path / ".claude").mkdir(parents=True)
        settings = tmp_path / ".claude" / "settings.json"
        settings.write_text("{}")
        (tmp_path / "CLAUDE.md").write_text("content")
        (tmp_path / ".gitignore").write_text("content")

        results = validate_scaffold(manifest, ["test"], tmp_path)
        file_checks = [
            (check, passed) for check, passed, msg in results if check == "file_exists"
        ]
        assert any(not passed for _, passed in file_checks)

    def test_invalid_settings_json_detected(self, tmp_path):
        manifest = {"modules": {"test": {"files": [], "dirs": [], "snippets": {}}}}
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "settings.json").write_text("not json")
        (tmp_path / "CLAUDE.md").write_text("content")
        (tmp_path / ".gitignore").write_text("content")

        results = validate_scaffold(manifest, ["test"], tmp_path)
        json_checks = [
            (check, passed)
            for check, passed, msg in results
            if check == "settings_json_valid"
        ]
        assert any(not passed for _, passed in json_checks)

    def test_missing_claude_md_detected(self, tmp_path):
        manifest = {"modules": {"test": {"files": [], "dirs": [], "snippets": {}}}}
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "settings.json").write_text("{}")
        (tmp_path / ".gitignore").write_text("content")
        # No CLAUDE.md

        results = validate_scaffold(manifest, ["test"], tmp_path)
        claude_checks = [
            (check, passed) for check, passed, msg in results if check == "claude_md"
        ]
        assert any(not passed for _, passed in claude_checks)

    def test_missing_gitignore_detected(self, tmp_path):
        manifest = {"modules": {"test": {"files": [], "dirs": [], "snippets": {}}}}
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "settings.json").write_text("{}")
        (tmp_path / "CLAUDE.md").write_text("content")
        # No .gitignore

        results = validate_scaffold(manifest, ["test"], tmp_path)
        gi_checks = [
            (check, passed) for check, passed, msg in results if check == "gitignore"
        ]
        assert any(not passed for _, passed in gi_checks)

    def test_no_github_scaffold_validates(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=False)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        results = validate_scaffold(manifest, modules, tmp_path)
        failures = [(check, msg) for check, passed, msg in results if not passed]
        assert failures == [], f"Validation failures: {failures}"
