"""scaffold repo command — scaffold AI infrastructure into a GitHub repo."""

import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import click

from display_lib.output import (
    Spinner,
    error,
    header,
    info,
    success,
    warn,
)
from tree_lib import TaskEntry, run_task, tree_fail, tree_group, tree_ok
from lib.assembler import print_report, scaffold_to_dir
from lib.display import print_file_tree
from lib.paths import get_scaf_data_dir, require_source_repo
from lib.errors import (
    EXIT_CONFLICT,
    EXIT_ENVIRONMENT,
    EXIT_REFERENCE,
    EXIT_RUNTIME,
)
from lib.manifest import (
    check_source_files,
    load_manifest,
    resolve_modules,
    validate_manifest,
)
from lib.validator import validate_scaffold

# Module-level flags, set by command options
_verbose = False
_timeout = 30


def _run(cmd, cwd=None, timeout=None):
    """Run subprocess, return result. Catches timeout cleanly."""
    if timeout is None:
        timeout = _timeout
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        cmd_str = " ".join(cmd[:3])
        error(f"Command timed out after {timeout}s: {cmd_str}")
        if _verbose:
            info(f"Full command: {' '.join(cmd)}")
        raise SystemExit(EXIT_RUNTIME)


def _run_preflight():
    """Run all preflight checks with spinner and tree output."""
    checks = [
        ("git installed", _check_git),
        ("gh CLI installed", _check_gh),
        ("GitHub authenticated", _check_gh_auth),
        ("GitHub API reachable", _check_gh_network),
        ("SSH connected to GitHub", _check_ssh),
    ]

    ssh_warning = None

    if _verbose:
        tree_group("Preflight checks")
        for i, (label, fn) in enumerate(checks):
            is_last = i == len(checks) - 1
            try:
                warning = run_task(
                    TaskEntry(
                        label=label,
                        action=fn,
                        spin=True,
                        is_last=is_last,
                        indent=_INDENT,
                    )
                )
            except SystemExit:
                raise
            if warning:
                ssh_warning = warning
    else:
        with Spinner("Preflight checks..."):
            for _label, fn in checks:
                warning = fn()
                if warning:
                    ssh_warning = warning
        success("Preflight checks")

    if ssh_warning:
        info(ssh_warning)


def _check_git():
    """Check git is installed."""
    result = subprocess.run(["which", "git"], capture_output=True, text=True)
    if result.returncode != 0:
        error("git not installed")
        raise SystemExit(EXIT_ENVIRONMENT)
    return None


def _check_gh():
    """Check gh CLI is installed."""
    result = subprocess.run(["which", "gh"], capture_output=True, text=True)
    if result.returncode != 0:
        error("GitHub CLI not installed. See https://cli.github.com/")
        raise SystemExit(EXIT_ENVIRONMENT)
    return None


def _check_gh_auth():
    """Check gh CLI authentication."""
    result = _run(["gh", "auth", "status"])
    if result.returncode != 0:
        error("Not authenticated")
        info("Fix: gh auth login")
        raise SystemExit(EXIT_ENVIRONMENT)
    return None


def _check_gh_network():
    """Check network connectivity to GitHub."""
    result = _run(["gh", "api", "user"])
    if result.returncode != 0:
        error("Cannot reach GitHub API")
        info("Fix: Check network connectivity")
        raise SystemExit(EXIT_ENVIRONMENT)
    return None


def _check_ssh():
    """Verify SSH connectivity to GitHub.

    Returns None on success, a warning string if passphrase is needed,
    or raises SystemExit on hard failure.
    """
    result = _run(["ssh", "-T", "-o", "BatchMode=yes", "git@github.com"], timeout=10)
    stderr = result.stderr or ""

    # GitHub returns exit code 1 with success message (no shell access)
    if "successfully authenticated" in stderr.lower():
        return None

    # Changed host key — security concern, do not suggest auto-fix
    if "REMOTE HOST IDENTIFICATION HAS CHANGED" in stderr:
        error("GitHub SSH host key has changed")
        warn(
            "Do not auto-fix. Investigate — this could indicate a security issue. "
            "See ~/.ssh/known_hosts"
        )
        raise SystemExit(EXIT_ENVIRONMENT)

    # Missing host fingerprint
    if "Host key verification failed" in stderr:
        error("GitHub not in known hosts")
        info("Fix: ssh-keyscan github.com >> ~/.ssh/known_hosts")
        raise SystemExit(EXIT_ENVIRONMENT)

    # Network issues
    if "Connection timed out" in stderr or "Connection refused" in stderr:
        error("Cannot reach github.com via SSH")
        info("Fix: Check network/firewall access to github.com:22")
        raise SystemExit(EXIT_ENVIRONMENT)

    # SSH agent issues
    if "Could not open" in stderr:
        error("SSH agent not running")
        info("Fix: eval $(ssh-agent) && ssh-add")
        raise SystemExit(EXIT_ENVIRONMENT)

    # Permission denied with BatchMode — key needs passphrase or not on GitHub
    if "Permission denied" in stderr:
        # This could be: passphrase-protected key (agent doesn't have it)
        # or key not on GitHub. We can't distinguish without prompting.
        # Warn and continue — if the key is wrong, git push will catch it.
        return "SSH key requires passphrase \u2014 you will be prompted during git operations"

    # Unknown SSH error
    error("SSH check failed")
    info(f"SSH error: {stderr.strip()}")
    raise SystemExit(EXIT_ENVIRONMENT)


_INDENT = "  "


def _repo_exists(name):
    """Check if a GitHub repo exists."""
    result = _run(["gh", "repo", "view", name])
    return result.returncode == 0


def _find_conflicts(repo_dir, manifest, modules):
    """Find files that already exist in the repo."""
    conflicts = []
    for mod_name in modules:
        module = manifest["modules"][mod_name]
        for file_entry in module["files"]:
            dest = Path(repo_dir) / file_entry["dest"]
            if dest.exists():
                conflicts.append(file_entry["dest"])

    # Check assembled files too
    for name in ["CLAUDE.md", ".gitignore", ".claude/settings.json"]:
        if (Path(repo_dir) / name).exists():
            conflicts.append(name)

    return conflicts


def _build_pr_body(manifest: dict, modules: list[str]) -> str:
    """Build PR body from manifest content."""
    mod_descriptions = {
        "base": "CLAUDE.md directives, settings, .gitignore",
        "planning": "PRP workflow: /generate-prp, /execute-prp, /peer-review-plan, templates",
        "priming": "Context generation: /prime-full, /prime-quick, /generate-context, /generate-arch",
        "github": "CI provenance: gh-dispatch-ai.yml, git-ai.sh, Mark agent",
        "changelog": "CHANGELOG.md with changelog-manager agent",
        "scripts": "Stack management (stack.sh), test runner (run-tests.sh)",
        "documentation": "Agentic workflow docs, CLI coding standards",
        "example": "Example backend (CRUD API) + CLI tool with full test foundations",
    }

    lines = [
        "## What this adds",
        "",
        "Agentic AI infrastructure for Claude Code \u2014 slash commands, agents, "
        "planning system, codebase priming, and a self-closing development cycle.",
        "",
        "## Modules",
        "",
    ]
    for mod in modules:
        desc = mod_descriptions.get(mod, "")
        lines.append(f"- **{mod}** \u2014 {desc}" if desc else f"- **{mod}**")

    # After merge
    lines.append("")
    lines.append("## After merge")
    lines.append("")
    step = 1
    if "github" in modules:
        lines.append(
            f"{step}. **GitHub secrets** (for provenance workflow): "
            "`PROVENANCE_APP_ID`, `PROVENANCE_APP_PRIVATE_KEY`, "
            "`PROVENANCE_INSTALLATION_ID`"
        )
        step += 1
    lines.append(f"{step}. Run `/prime-full` to generate initial codebase context")
    step += 1
    lines.append(f"{step}. See `docs/agentic-workflow/` for usage guide")

    return "\n".join(lines)


@click.command()
@click.argument("name")
@click.option("--no-github", is_flag=True, help="Exclude github module")
@click.option(
    "--no-backend-lib", is_flag=True, help="Exclude backend-lib shared library"
)
@click.option(
    "-p",
    "--private-repo",
    "visibility",
    flag_value="private",
    default=True,
    help="Private repo (default)",
)
@click.option(
    "-P", "--public-repo", "visibility", flag_value="public", help="Public repo"
)
@click.option("-y", "auto_confirm", is_flag=True, help="Skip confirmation prompts")
@click.option(
    "-r",
    "--repo-description",
    "description",
    default=None,
    help="Repo description (required for new repos)",
)
@click.option(
    "--force", is_flag=True, help="Overwrite conflicting files in existing repos"
)
@click.option("--dry-run", "-n", is_flag=True, help="Show plan without executing")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
@click.option(
    "--timeout",
    default=30,
    show_default=True,
    type=int,
    help="Timeout in seconds per operation",
)
def repo_cmd(
    name,
    no_github,
    no_backend_lib,
    visibility,
    auto_confirm,
    description,
    force,
    dry_run,
    verbose,
    timeout,
):
    """Scaffold AI infrastructure into a GitHub repo."""
    global _verbose, _timeout
    _verbose = verbose
    _timeout = timeout

    source_repo = require_source_repo()
    scaf_data = get_scaf_data_dir()
    today = date.today().isoformat()
    branch_name = f"scaffold-ai-{today}"

    header("Scaffold Repo")

    # Preflight checks (skipped on dry-run)
    if not dry_run:
        _run_preflight()

    # Load and validate manifest
    manifest = load_manifest(scaf_data / "manifest.json")
    validate_manifest(manifest, scaf_data / "schemas" / "manifest.schema.json")
    modules = resolve_modules(
        manifest,
        include_github=not no_github,
        include_backend_lib=not no_backend_lib,
    )

    # Check source files
    missing = check_source_files(manifest, modules, source_repo)
    if missing:
        for f in missing:
            error(f"Missing source file: {f}")
        raise SystemExit(EXIT_REFERENCE)

    # Check repo existence
    repo_exists = _repo_exists(name) if not dry_run else False

    if dry_run:
        info(f"[dry-run] Target repo: {name}")
        info(f"[dry-run] Branch: {branch_name}")
        info(f"[dry-run] Visibility: {visibility}")
        info(f"[dry-run] Modules: {', '.join(modules)}")
        return

    tmpdir = tempfile.mkdtemp(prefix="scafcli-")
    try:
        if repo_exists:
            # Existing repo flow
            if not auto_confirm:
                info(f"Repo '{name}' exists \u2014 will scaffold into it")
                info(f"Modules: {', '.join(modules)}")
                if click.confirm(
                    "Preview file tree before scaffolding existing repository?"
                ):
                    print_file_tree(manifest, modules, source_repo)
                if not click.confirm(
                    "Scaffold existing repository with agentic infrastructure?"
                ):
                    info("Aborted.")
                    return

            tree_group("Scaffold (existing repo)")
            run_task(
                TaskEntry(
                    label=f"Cloned {name}",
                    action=lambda: _run(["gh", "repo", "clone", name, tmpdir]),
                    indent=_INDENT,
                )
            )

            # Check for conflicts
            conflicts = _find_conflicts(tmpdir, manifest, modules)
            if conflicts and not force:
                tree_fail("Conflict check", indent=_INDENT)
                error("Conflicting files found (use --force to overwrite):")
                for c in conflicts:
                    error(f"  {c}")
                raise SystemExit(EXIT_CONFLICT)
            elif conflicts:
                warn(f"  Overwriting {len(conflicts)} conflicting file(s) (--force)")
        else:
            # New repo flow
            if not description:
                error("--repo-description / -r is required when creating a new repo")
                raise SystemExit(EXIT_RUNTIME)

            vis_label = visibility if visibility else "private"

            if not auto_confirm:
                info(f"Will create repo '{name}' ({vis_label})")
                info(f"Modules: {', '.join(modules)}")
                if click.confirm(
                    "Preview file tree before creating remote repository?"
                ):
                    print_file_tree(manifest, modules, source_repo)
                if not click.confirm(
                    "Create remote GitHub repository with agentic scaffolding?"
                ):
                    info("Aborted.")
                    return

            tree_group("Scaffold (new repo)")
            create_cmd = [
                "gh",
                "repo",
                "create",
                name,
                "--add-readme",
                "--description",
                description,
                f"--{vis_label}",
            ]
            run_task(
                TaskEntry(
                    label=f"Creating {name}",
                    action=lambda: _run(create_cmd),
                    spin=True,
                    done_label=f"Created {name} ({vis_label})",
                    indent=_INDENT,
                )
            )

            # Clone into tmpdir
            shutil.rmtree(tmpdir)
            run_task(
                TaskEntry(
                    label="Cloned",
                    action=lambda: _run(["gh", "repo", "clone", name, tmpdir]),
                    indent=_INDENT,
                )
            )

        # Create branch (retry with suffix if name taken)
        def _create_branch():
            nonlocal branch_name
            for suffix in ["", "-2", "-3", "-4", "-5"]:
                attempt = f"{branch_name}{suffix}"
                result = _run(["git", "checkout", "-b", attempt], cwd=tmpdir)
                if result.returncode == 0:
                    branch_name = attempt
                    return result
            return result  # last failed attempt

        result = _create_branch()
        if isinstance(result, subprocess.CompletedProcess) and result.returncode != 0:
            tree_fail("Branch creation", indent=_INDENT)
            error("All branch name suffixes taken")
            raise SystemExit(EXIT_RUNTIME)
        tree_ok(f"Branch: {branch_name}", indent=_INDENT)

        # Scaffold files
        report = run_task(
            TaskEntry(
                label="Scaffolded",
                action=lambda: scaffold_to_dir(
                    manifest, modules, source_repo, Path(tmpdir)
                ),
                indent=_INDENT,
            )
        )

        # Report scaffolded trees
        for td in report.get("template_dirs_created", []):
            tree_ok(
                f"Scaffolded: {td['dest']}/ ({td['file_count']} files)",
                indent=_INDENT,
            )

        # Validate
        def _validate():
            results = validate_scaffold(manifest, modules, Path(tmpdir))
            if not all(passed for _, passed, _ in results):
                failed = [msg for _, passed, msg in results if not passed]
                raise RuntimeError("\n".join(failed))
            return results

        run_task(
            TaskEntry(
                label="Validated",
                action=_validate,
                is_last=True,
                indent=_INDENT,
            )
        )

        # Confirm commit/push/PR
        if not auto_confirm:
            if not click.confirm("Commit, push, and create PR?"):
                info("Aborted.")
                return

        # Publish
        tree_group("Publish")

        def _commit():
            _run(["git", "add", "-A"], cwd=tmpdir)
            return _run(
                ["git", "commit", "-m", "Scaffold AI infrastructure"], cwd=tmpdir
            )

        run_task(
            TaskEntry(
                label="Committed",
                action=_commit,
                indent=_INDENT,
            )
        )

        def _handle_push_fail(cause):
            stderr = cause.stderr.strip() if hasattr(cause, "stderr") else str(cause)
            if "Permission denied" in stderr:
                error("SSH key not recognized by GitHub")
                info("Fix: Add your SSH key to your GitHub account settings")
            else:
                error(stderr)
            raise SystemExit(EXIT_RUNTIME)

        run_task(
            TaskEntry(
                label="Pushed",
                action=lambda: _run(
                    ["git", "push", "-u", "origin", branch_name],
                    cwd=tmpdir,
                ),
                on_fail=_handle_push_fail,
                indent=_INDENT,
            )
        )

        # Create PR (or detect existing)
        existing = _run(
            ["gh", "pr", "view", branch_name, "--json", "url", "-q", ".url"],
            cwd=tmpdir,
        )
        if existing.returncode == 0 and existing.stdout.strip():
            pr_url = existing.stdout.strip()
            tree_ok(f"PR already exists: {pr_url}", is_last=True, indent=_INDENT)
        else:
            pr_body = _build_pr_body(manifest, modules)

            def _create_pr():
                result = _run(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--title",
                        "Scaffold AI infrastructure",
                        "--body",
                        pr_body,
                    ],
                    cwd=tmpdir,
                )
                if (
                    isinstance(result, subprocess.CompletedProcess)
                    and result.returncode != 0
                ):
                    # PR create reported failure — check if it was created anyway
                    verify = _run(
                        [
                            "gh",
                            "pr",
                            "view",
                            branch_name,
                            "--json",
                            "url",
                            "-q",
                            ".url",
                        ],
                        cwd=tmpdir,
                    )
                    if verify.returncode == 0 and verify.stdout.strip():
                        return verify
                    return result
                return result

            result = run_task(
                TaskEntry(
                    label="Creating PR",
                    action=_create_pr,
                    spin=True,
                    done_label="PR created",
                    is_last=True,
                    indent=_INDENT,
                )
            )
            pr_url = result.stdout.strip()

        # Report
        header("Scaffold Complete")
        success(f"PR: {pr_url}")
        if _verbose:
            print_file_tree(manifest, modules, source_repo)
            print_report(report)

        # Post-scaffold github setup steps
        if "github" in modules:
            info("")
            info("To enable the provenance workflow (Mark agent):")
            info(
                "1. Merge the scaffold PR \u2014 the workflow must exist on main before it can run"
            )
            info(
                "2. Configure 3 GitHub secrets: PROVENANCE_APP_ID, PROVENANCE_APP_PRIVATE_KEY, PROVENANCE_INSTALLATION_ID"
            )
            info(
                "   Setup guide (steps 1-6): https://github.com/apolopena/github-workflows/blob/main/README.md"
            )
            info(
                "3. Mark can now dispatch the provenance workflow for PRs, issues, and comments"
            )

        info("")
        info(
            "Once you have code in your repo, run `/prime-full` to generate codebase context."
        )

    finally:
        # Clean up temp dir
        if Path(tmpdir).exists():
            shutil.rmtree(tmpdir, ignore_errors=True)
