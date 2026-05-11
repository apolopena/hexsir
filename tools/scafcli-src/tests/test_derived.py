"""Tests for template and template_dirs scaffolding."""

import stat

from lib.assembler import scaffold_to_dir
from lib.manifest import resolve_modules
from lib.validator import validate_scaffold


class TestTemplateDirs:
    def test_template_dirs_copied(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        report = scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        dests = [td["dest"] for td in report["template_dirs_created"]]
        assert "tools/scafcli-src" in dests
        assert "tools/shared/display-lib" in dests
        assert "tools/shared/tree-lib" in dests

    def test_scafcli_files_exist(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        assert (tmp_path / "tools" / "scafcli-src" / "cli.py").exists()
        assert (tmp_path / "tools" / "scafcli-src" / "pyproject.toml").exists()
        assert (tmp_path / "tools" / "scafcli-src" / "commands" / "repo.py").exists()
        assert (tmp_path / "tools" / "scafcli-src" / "data" / "manifest.json").exists()

    def test_shared_libs_exist(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        assert (
            tmp_path / "tools" / "shared" / "display-lib" / "pyproject.toml"
        ).exists()
        assert (
            tmp_path / "tools" / "shared" / "display-lib" / "display_lib" / "output.py"
        ).exists()
        assert (tmp_path / "tools" / "shared" / "tree-lib" / "pyproject.toml").exists()
        assert (
            tmp_path / "tools" / "shared" / "tree-lib" / "tree_lib" / "__init__.py"
        ).exists()

    def test_every_shared_lib_is_in_manifest(self, manifest, source_repo):
        """Every tools/shared/<lib> on disk must be scaffolded by the manifest.
        Shared libraries ship verbatim — they are scaffolding, not templates.
        A shared lib missing from the manifest means any tool built with its
        --include-* flag will have broken imports in the scaffolded repo."""
        shared_root = source_repo / "tools" / "shared"
        on_disk = {
            d.name
            for d in shared_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        }

        in_manifest = set()
        for module in manifest["modules"].values():
            for td in module.get("template_dirs", []):
                src = td["src"]
                if src.startswith("tools/shared/"):
                    in_manifest.add(src.split("/", 2)[2])

        missing = on_disk - in_manifest
        assert not missing, (
            f"Shared libraries on disk but not scaffolded by the manifest: "
            f"{sorted(missing)}"
        )

    def test_docs_merged_with_module_files(self, manifest, source_repo, tmp_path):
        """Documentation module copies priming.md as a file,
        and README.md as template — all should coexist."""
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        docs_dir = tmp_path / "docs" / "agentic-workflow"
        assert (docs_dir / "README.md").exists()
        assert (docs_dir / "development-cycle.md").exists()
        assert (docs_dir / "priming.md").exists()

    def test_docs_readme_exists(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        assert (tmp_path / "docs" / "README.md").exists()
        assert (tmp_path / "docs" / "tools" / "coding-standards.md").exists()
        assert (tmp_path / "docs" / "tools" / "creating-a-new-tool.md").exists()

    def test_run_tests_sh_executable(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        run_tests = tmp_path / "scripts" / "run-tests.sh"
        assert run_tests.exists()
        assert run_tests.stat().st_mode & stat.S_IXUSR

    def test_scafcli_wrapper_executable(self, manifest, source_repo, tmp_path):
        modules = resolve_modules(manifest, include_github=True)
        scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        wrapper = tmp_path / "tools" / "scafcli"
        assert wrapper.exists()
        assert wrapper.stat().st_mode & stat.S_IXUSR

    def test_scaffold_without_templates(self, source_repo, tmp_path):
        """Manifest without templates/template_dirs should still work."""
        manifest = {
            "modules": {
                "base": {
                    "files": [],
                    "dirs": [".claude/"],
                    "snippets": {},
                }
            }
        }
        report = scaffold_to_dir(manifest, ["base"], source_repo, tmp_path)
        assert report["template_dirs_created"] == []
        assert report["templates_created"] == ["CLAUDE.md", ".gitignore"]


class TestTemplateDirValidation:
    def test_missing_template_dir_detected(self, tmp_path):
        manifest = {
            "modules": {
                "test": {
                    "files": [],
                    "dirs": [],
                    "snippets": {},
                    "template_dirs": [
                        {"src": "does/not/matter", "dest": "missing-dir"}
                    ],
                }
            }
        }
        results = validate_scaffold(manifest, ["test"], tmp_path)
        td_checks = [
            (check, passed)
            for check, passed, _ in results
            if check == "template_dir_exists"
        ]
        assert any(not passed for _, passed in td_checks)
