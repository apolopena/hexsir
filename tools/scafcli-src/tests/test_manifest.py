"""Tests for lib_scaf/manifest.py."""

import pytest

from lib.manifest import (
    check_source_files,
    load_manifest,
    resolve_modules,
    validate_manifest,
)


class TestLoadManifest:
    def test_loads_valid_manifest(self, manifest_path):
        result = load_manifest(manifest_path)
        assert "modules" in result
        assert "base" in result["modules"]

    def test_exits_on_missing_file(self, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            load_manifest(tmp_path / "nonexistent.json")
        assert exc_info.value.code == 1

    def test_exits_on_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json")
        with pytest.raises(SystemExit) as exc_info:
            load_manifest(bad_file)
        assert exc_info.value.code == 1


class TestValidateManifest:
    def test_valid_manifest_passes(self, manifest, schema_path):
        # Should not raise
        validate_manifest(manifest, schema_path)

    def test_invalid_manifest_exits(self, schema_path):
        with pytest.raises(SystemExit) as exc_info:
            validate_manifest({"bad": "data"}, schema_path)
        assert exc_info.value.code == 1

    def test_empty_modules_exits(self, schema_path):
        with pytest.raises(SystemExit) as exc_info:
            validate_manifest({"modules": {}}, schema_path)
        assert exc_info.value.code == 1


class TestResolveModules:
    def test_all_modules_included(self, manifest):
        modules = resolve_modules(manifest, include_github=True)
        expected = [
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
        assert modules == expected

    def test_github_excluded(self, manifest):
        modules = resolve_modules(manifest, include_github=False)
        assert "github" not in modules
        expected = [
            "base",
            "planning",
            "priming",
            "changelog",
            "scripts",
            "documentation",
            "tooling",
            "backend-lib",
        ]
        assert modules == expected

    def test_backend_lib_excluded(self, manifest):
        modules = resolve_modules(manifest, include_backend_lib=False)
        assert "backend-lib" not in modules
        assert "tooling" in modules

    def test_order_preserved(self, manifest):
        modules = resolve_modules(manifest)
        assert modules.index("base") < modules.index("planning")
        assert modules.index("planning") < modules.index("priming")
        assert modules.index("priming") < modules.index("github")
        assert modules.index("github") < modules.index("changelog")
        assert modules.index("changelog") < modules.index("scripts")
        assert modules.index("scripts") < modules.index("documentation")
        assert modules.index("documentation") < modules.index("tooling")
        assert modules.index("tooling") < modules.index("backend-lib")


class TestCheckSourceFiles:
    def test_all_files_exist(self, manifest, source_repo):
        modules = resolve_modules(manifest, include_github=True)
        missing = check_source_files(manifest, modules, source_repo)
        assert missing == [], f"Missing files: {missing}"

    def test_detects_missing_file(self, source_repo):
        manifest = {
            "modules": {
                "test": {
                    "files": [{"src": "nonexistent/file.txt", "dest": "file.txt"}],
                    "dirs": [],
                    "snippets": {},
                }
            }
        }
        missing = check_source_files(manifest, ["test"], source_repo)
        assert "nonexistent/file.txt" in missing

    def test_detects_missing_snippet(self, source_repo):
        manifest = {
            "modules": {
                "test": {
                    "files": [],
                    "dirs": [],
                    "snippets": {"claude": "nonexistent/snippet.md"},
                }
            }
        }
        missing = check_source_files(manifest, ["test"], source_repo)
        assert "nonexistent/snippet.md" in missing

    def test_derived_source_dirs_exist(self, manifest, source_repo):
        modules = resolve_modules(manifest, include_github=True)
        missing = check_source_files(manifest, modules, source_repo)
        assert missing == [], f"Missing derived sources: {missing}"

    def test_detects_missing_template_dir_source(self, source_repo):
        manifest = {
            "modules": {
                "test": {
                    "files": [],
                    "dirs": [],
                    "snippets": {},
                    "template_dirs": [{"src": "nonexistent/dir", "dest": "output"}],
                }
            }
        }
        missing = check_source_files(manifest, ["test"], source_repo)
        assert "nonexistent/dir" in missing

    def test_manifest_with_templates_passes_schema(self, schema_path):
        manifest = {
            "modules": {
                "test": {
                    "files": [],
                    "dirs": [],
                    "snippets": {},
                    "templates": [{"src": "some/file.md", "dest": "output.md"}],
                    "template_dirs": [{"src": "some/dir", "dest": "output"}],
                }
            }
        }
        validate_manifest(manifest, schema_path)

    def test_manifest_without_templates_passes_schema(self, schema_path):
        manifest = {"modules": {"test": {"files": [], "dirs": [], "snippets": {}}}}
        validate_manifest(manifest, schema_path)
