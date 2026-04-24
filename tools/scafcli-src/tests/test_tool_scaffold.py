"""Tests for scaffold tool command."""

import ast
import os
import stat
import subprocess
from pathlib import Path

import pytest
import tomllib
from click.testing import CliRunner

from cli import cli
from test_lib.cli import assert_cli_ok


def _scaffold(runner, tool_name, command_name="status", *extra_args, **kwargs):
    """Invoke scaffold tool with given name and extra args."""
    return runner.invoke(
        cli, ["tool", "new", tool_name, command_name, *extra_args], **kwargs
    )


class TestToolScaffold:
    """Tests for scafcli scaffold tool."""

    def test_creates_all_files(self, tmp_path, monkeypatch):
        """Scaffold creates all expected files."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        result = _scaffold(runner, "testtoolcli", "audit")
        assert_cli_ok(result)

        src = tools_dir / "testtoolcli-src"
        assert (src / "cli.py").exists()
        assert (src / "pyproject.toml").exists()
        assert (src / "commands" / "__init__.py").exists()
        assert (src / "commands" / "audit.py").exists()
        assert (src / "lib" / "__init__.py").exists()
        assert (src / "data" / "__init__.py").exists()
        assert (src / "tests" / "conftest.py").exists()
        assert (src / "tests" / "unit" / "__init__.py").exists()
        assert (src / "tests" / "unit" / "test_cli.py").exists()
        assert (src / "tests" / "unit" / "test_audit.py").exists()
        assert (src / "CHANGELOG.md").exists()
        assert (tools_dir / "testtoolcli").exists()

    def test_pyproject_valid_toml(self, tmp_path, monkeypatch):
        """Generated pyproject.toml is valid TOML with commands package."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        _scaffold(runner, "testtoolcli", "audit")

        pyproject = tools_dir / "testtoolcli-src" / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        assert data["project"]["name"] == "testtoolcli-src"
        assert data["project"]["version"] == "0.1.0"
        assert "commands" in data["tool"]["setuptools"]["packages"]

    def test_cli_py_lints_clean(self, tmp_path, monkeypatch):
        """Generated cli.py passes ruff check (no F401 unused imports)."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        _scaffold(runner, "testtoolcli", "audit")

        cli_py = tools_dir / "testtoolcli-src" / "cli.py"
        result = subprocess.run(
            ["ruff", "check", str(cli_py), "--select", "F401"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"ruff found unused imports:\n{result.stdout}"

        # Also check command stub
        cmd_py = tools_dir / "testtoolcli-src" / "commands" / "audit.py"
        result = subprocess.run(
            ["ruff", "check", str(cmd_py), "--select", "F401"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"ruff found unused imports in command stub:\n{result.stdout}"
        )

    def test_generated_test_passes(self):
        """Scaffolded test passes when run with pytest.

        Uses the real repo root so uv sync can resolve shared lib paths.
        """
        from lib.paths import get_root_dir

        repo_root = get_root_dir()
        tools_dir = repo_root / "tools"
        name = "scaftestcli"
        src = tools_dir / f"{name}-src"
        wrapper = tools_dir / name

        try:
            runner = CliRunner()
            result = _scaffold(runner, name, "status")
            assert_cli_ok(result)

            test_result = subprocess.run(
                [str(src / ".venv" / "bin" / "pytest"), "tests/", "-v"],
                cwd=str(src),
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(src)},
            )
            assert test_result.returncode == 0, (
                f"Tests failed:\n{test_result.stdout}\n{test_result.stderr}"
            )
        finally:
            import shutil

            if src.exists():
                shutil.rmtree(src)
            if wrapper.exists():
                wrapper.unlink()

    def test_no_backend_flag_minimal_wrapper(self, tmp_path, monkeypatch):
        """Non-backend wrapper exports CLI_ROOT_DIR but no backend URLs."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        _scaffold(runner, "testtoolcli", "audit")

        wrapper = (tools_dir / "testtoolcli").read_text()
        assert "CLI_ROOT_DIR" in wrapper
        assert "CLI_BACKEND_URL" not in wrapper

    def test_dry_run_no_files(self, tmp_path, monkeypatch):
        """--dry-run creates nothing."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)

        runner = CliRunner()
        result = _scaffold(runner, "testtoolcli", "audit", "--dry-run")

        assert_cli_ok(result)
        assert "Would create:" in result.output
        assert not (tools_dir / "testtoolcli-src").exists()
        assert not (tools_dir / "testtoolcli").exists()

    def test_existing_dir_aborts(self, tmp_path, monkeypatch):
        """Error when directory already exists."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "testtoolcli-src").mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)

        runner = CliRunner()
        result = _scaffold(runner, "testtoolcli", "audit")

        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_wrapper_is_executable(self, tmp_path, monkeypatch):
        """Bash wrapper has execute bit set."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        _scaffold(runner, "testtoolcli", "audit")

        wrapper = tools_dir / "testtoolcli"
        mode = wrapper.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_invalid_name_rejected(self, tmp_path, monkeypatch):
        """Names without cli suffix, digits, hyphens, uppercase are rejected."""
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)

        runner = CliRunner()

        for bad_name in [
            "Bad Name",
            "UPPER",
            "has space",
            "trail-",
            "-lead",
            "foo@bar",
            "demo",
            "tool-cli",
            "demo2cli",
            "DemoCli",
            "123cli",
        ]:
            result = _scaffold(runner, bad_name, "audit")
            assert result.exit_code != 0, f"Name '{bad_name}' should have been rejected"

    def test_command_name_validation(self, tmp_path, monkeypatch):
        """Invalid command names are rejected."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)

        runner = CliRunner()

        for bad_cmd in ["-lead", "trail-", "BAD", "has space", "foo@bar"]:
            result = _scaffold(runner, "testtoolcli", bad_cmd)
            assert result.exit_code != 0, (
                f"Command '{bad_cmd}' should have been rejected"
            )

    def test_hyphen_command_name(self, tmp_path, monkeypatch):
        """Hyphenated command names produce underscored files and functions."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        result = _scaffold(runner, "testtoolcli", "check-status")
        assert_cli_ok(result)

        src = tools_dir / "testtoolcli-src"
        assert (src / "commands" / "check_status.py").exists()
        assert (src / "tests" / "unit" / "test_check_status.py").exists()

        cmd_content = (src / "commands" / "check_status.py").read_text()
        assert "check_status_cmd" in cmd_content

        cli_content = (src / "cli.py").read_text()
        assert 'name="check-status"' in cli_content
        assert "check_status.check_status_cmd" in cli_content

    def test_include_repl_flag(self, tmp_path, monkeypatch):
        """--include-repl adds REPL dispatch to cli.py and repl-lib to deps."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        result = _scaffold(runner, "testtoolcli", "audit", "--include-repl")
        assert_cli_ok(result)

        src = tools_dir / "testtoolcli-src"
        cli_content = (src / "cli.py").read_text()
        assert "_CLICK_COMMANDS" in cli_content
        assert "interactive" in cli_content
        assert "Repl" in cli_content

        pyproject = tomllib.loads((src / "pyproject.toml").read_text())
        dep_strs = pyproject["project"]["dependencies"]
        assert any("repl-lib" in d for d in dep_strs)

    def test_include_repl_lints_clean(self, tmp_path, monkeypatch):
        """Generated cli.py with REPL passes ruff check."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        _scaffold(runner, "testtoolcli", "audit", "--include-repl")

        cli_py = tools_dir / "testtoolcli-src" / "cli.py"
        result = subprocess.run(
            ["ruff", "check", str(cli_py), "--select", "F401,E"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"ruff errors in REPL cli.py:\n{result.stdout}"

    def test_help_text_shows_command(self, tmp_path, monkeypatch):
        """Scaffold output --help shows command name."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["tool", "new", "--help"])
        assert_cli_ok(result)
        assert "TOOL_NAME" in result.output
        assert "COMMAND_NAME" in result.output

    def test_post_create_shows_cli_tools_registration(self, tmp_path, monkeypatch):
        """Post-create message shows CLI_TOOLS registration."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        result = _scaffold(runner, "testtoolcli", "audit")
        assert_cli_ok(result)
        assert "CLI_TOOLS" in result.output
        assert '"testtoolcli"' in result.output

    def test_backend_available_false_when_missing(self, tmp_path, monkeypatch):
        """_backend_available returns False when backend-lib absent."""
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)

        from commands.tool import _backend_available

        assert _backend_available() is False

    def test_include_backend_conditional_on_backend_available(self):
        """--include-backend option only registered when _BACKEND_AVAILABLE is True."""
        from commands.tool import _BACKEND_AVAILABLE, tool_cmd

        param_names = [p.name for p in tool_cmd.params]
        if _BACKEND_AVAILABLE:
            assert "include_backend" in param_names
        else:
            assert "include_backend" not in param_names


class TestTemplateRendering:
    """Verify rendered templates are syntactically valid Python."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )
        self.tmp_path = tmp_path
        self.tools_dir = tools_dir

    def _parse_py(self, path):
        """Assert file is parseable Python via ast.parse."""
        source = path.read_text()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"{path.name} is not valid Python:\n{e}\n\n{source}")

    def test_base_cli_py_parses(self):
        """Base scaffold cli.py is valid Python."""
        runner = CliRunner()
        _scaffold(runner, "testtoolcli", "audit")
        self._parse_py(self.tools_dir / "testtoolcli-src" / "cli.py")

    def test_repl_cli_py_parses(self):
        """REPL scaffold cli.py is valid Python."""
        runner = CliRunner()
        _scaffold(runner, "testtoolcli", "audit", "--include-repl")
        self._parse_py(self.tools_dir / "testtoolcli-src" / "cli.py")

    def test_command_stub_parses(self):
        """Generated command stub is valid Python."""
        runner = CliRunner()
        _scaffold(runner, "testtoolcli", "check-status")
        self._parse_py(
            self.tools_dir / "testtoolcli-src" / "commands" / "check_status.py"
        )

    def test_command_test_parses(self):
        """Generated command test is valid Python."""
        runner = CliRunner()
        _scaffold(runner, "testtoolcli", "check-status")
        self._parse_py(
            self.tools_dir
            / "testtoolcli-src"
            / "tests"
            / "unit"
            / "test_check_status.py"
        )


class TestGoldenFiles:
    """Verify scaffold output matches golden-file snapshots."""

    FIXTURES = Path(__file__).parent / "fixtures"

    def _compare_tree(self, actual_dir, golden_dir):
        """Assert all golden files match actual output."""
        for golden_file in sorted(golden_dir.rglob("*")):
            if golden_file.is_dir():
                continue
            if "__pycache__" in str(golden_file) or golden_file.suffix == ".pyc":
                continue
            rel = golden_file.relative_to(golden_dir)
            actual_file = actual_dir / rel
            assert actual_file.exists(), f"Missing: {rel}"
            assert actual_file.read_text() == golden_file.read_text(), (
                f"Mismatch in {rel}:\n"
                f"--- golden ---\n{golden_file.read_text()}\n"
                f"--- actual ---\n{actual_file.read_text()}"
            )

    def _mock_date(self, monkeypatch):
        """Pin date for deterministic CHANGELOG."""

        class FakeDate:
            @staticmethod
            def today():
                class D:
                    def isoformat(self):
                        return "2025-01-01"

                return D()

        monkeypatch.setattr("commands.tool.date", FakeDate())

    def test_golden_basic(self, tmp_path, monkeypatch):
        """Basic scaffold matches golden snapshot."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )
        self._mock_date(monkeypatch)

        runner = CliRunner()
        _scaffold(runner, "demotoolcli", "audit")
        self._compare_tree(
            tools_dir / "demotoolcli-src",
            self.FIXTURES / "golden_basic",
        )
