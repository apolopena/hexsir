"""Tests for scaffold command subcommand."""

import subprocess

from click.testing import CliRunner

from cli import cli
from test_lib.cli import assert_cli_ok


def _scaffold_tool(runner, tool_name, command_name="mycommand", *extra_args):
    """Scaffold a tool to add commands to."""
    return runner.invoke(cli, ["tool", "new", tool_name, command_name, *extra_args])


def _add_command(runner, tool_name, command_name):
    """Add a command to an existing tool."""
    return runner.invoke(cli, ["tool", "add", "command", tool_name, command_name])


class TestCommandScaffold:
    """Tests for scafcli scaffold command."""

    def _setup_tool(self, tmp_path, monkeypatch, include_repl=False):
        """Scaffold a base tool and return (runner, tools_dir)."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.tool.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr("commands.command.get_root_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "commands.tool.subprocess.run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
        )

        runner = CliRunner()
        args = ["--include-repl"] if include_repl else []
        result = _scaffold_tool(runner, "testtoolcli", "mycommand", *args)
        assert_cli_ok(result)
        return runner, tools_dir

    def test_creates_command_and_test(self, tmp_path, monkeypatch):
        """Scaffold command creates both files."""
        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch)
        result = _add_command(runner, "testtoolcli", "billing")
        assert_cli_ok(result)

        src = tools_dir / "testtoolcli-src"
        assert (src / "commands" / "billing.py").exists()
        assert (src / "tests" / "unit" / "test_billing.py").exists()

    def test_command_stub_has_cmd_suffix(self, tmp_path, monkeypatch):
        """Generated command uses _cmd suffix."""
        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch)
        _add_command(runner, "testtoolcli", "billing")

        content = (
            tools_dir / "testtoolcli-src" / "commands" / "billing.py"
        ).read_text()
        assert "def billing_cmd" in content

    def test_hyphen_command_creates_underscored_files(self, tmp_path, monkeypatch):
        """Hyphenated command name creates underscored files."""
        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch)
        _add_command(runner, "testtoolcli", "check-status")

        src = tools_dir / "testtoolcli-src"
        assert (src / "commands" / "check_status.py").exists()
        assert (src / "tests" / "unit" / "test_check_status.py").exists()

        content = (src / "commands" / "check_status.py").read_text()
        assert "def check_status_cmd" in content

    def test_wires_into_cli_py(self, tmp_path, monkeypatch):
        """Auto-wires import and registration via markers."""
        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch)
        result = _add_command(runner, "testtoolcli", "billing")
        assert "Wired into cli.py" in result.output

        cli_content = (tools_dir / "testtoolcli-src" / "cli.py").read_text()
        assert "billing," in cli_content
        assert 'cli.add_command(billing.billing_cmd, name="billing")' in cli_content

    def test_wires_repl_commands(self, tmp_path, monkeypatch):
        """Auto-wires REPL dispatch for REPL tools."""
        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch, include_repl=True)
        _add_command(runner, "testtoolcli", "billing")

        cli_content = (tools_dir / "testtoolcli-src" / "cli.py").read_text()
        assert '"billing": billing.billing_cmd,' in cli_content

    def test_fallback_prints_instructions(self, tmp_path, monkeypatch):
        """Prints instructions when markers are missing."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.command.get_root_dir", lambda: tmp_path)

        # Create a tool dir with a cli.py that has no markers
        src = tools_dir / "testtoolcli-src"
        src.mkdir()
        (src / "commands").mkdir()
        (src / "tests" / "unit").mkdir(parents=True)
        (src / "cli.py").write_text("# no markers here\n")

        runner = CliRunner()
        result = _add_command(runner, "testtoolcli", "billing")
        assert_cli_ok(result)
        assert "Add to cli.py:" in result.output
        assert "Wired" not in result.output

    def test_rejects_invalid_command_name(self, tmp_path, monkeypatch):
        """Invalid command names are rejected."""
        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch)

        for bad_name in ["-lead", "trail-", "BAD", "has space"]:
            result = _add_command(runner, "testtoolcli", bad_name)
            assert result.exit_code != 0, (
                f"Command '{bad_name}' should have been rejected"
            )

    def test_rejects_nonexistent_tool(self, tmp_path, monkeypatch):
        """Error when tool directory doesn't exist."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        monkeypatch.setattr("commands.command.get_root_dir", lambda: tmp_path)

        runner = CliRunner()
        result = _add_command(runner, "notoolcli", "billing")
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_rejects_existing_command_file(self, tmp_path, monkeypatch):
        """Error when command file already exists."""
        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch)
        # mycommand already exists from scaffold tool
        result = _add_command(runner, "testtoolcli", "mycommand")
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_multiple_commands_wire_correctly(self, tmp_path, monkeypatch):
        """Adding two commands both appear in cli.py."""
        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch)
        _add_command(runner, "testtoolcli", "billing")
        _add_command(runner, "testtoolcli", "report")

        cli_content = (tools_dir / "testtoolcli-src" / "cli.py").read_text()
        assert "billing," in cli_content
        assert "report," in cli_content
        assert 'name="billing"' in cli_content
        assert 'name="report"' in cli_content

    def test_multiple_commands_repl_wire(self, tmp_path, monkeypatch):
        """Adding two commands to REPL tool wires both into dispatch."""
        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch, include_repl=True)
        _add_command(runner, "testtoolcli", "billing")
        _add_command(runner, "testtoolcli", "report")

        cli_content = (tools_dir / "testtoolcli-src" / "cli.py").read_text()
        assert '"billing": billing.billing_cmd,' in cli_content
        assert '"report": report.report_cmd,' in cli_content

    def test_wired_cli_py_is_valid_python(self, tmp_path, monkeypatch):
        """cli.py remains valid Python after wiring."""
        import ast

        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch)
        _add_command(runner, "testtoolcli", "billing")
        _add_command(runner, "testtoolcli", "report")

        cli_py = tools_dir / "testtoolcli-src" / "cli.py"
        try:
            ast.parse(cli_py.read_text())
        except SyntaxError as e:
            import pytest

            pytest.fail(f"cli.py is invalid Python after wiring:\n{e}")

    def test_wired_repl_cli_py_is_valid_python(self, tmp_path, monkeypatch):
        """REPL cli.py remains valid Python after wiring."""
        import ast

        runner, tools_dir = self._setup_tool(tmp_path, monkeypatch, include_repl=True)
        _add_command(runner, "testtoolcli", "billing")
        _add_command(runner, "testtoolcli", "check-status")

        cli_py = tools_dir / "testtoolcli-src" / "cli.py"
        try:
            ast.parse(cli_py.read_text())
        except SyntaxError as e:
            import pytest

            pytest.fail(f"REPL cli.py is invalid Python after wiring:\n{e}")
