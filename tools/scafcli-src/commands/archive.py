"""scaffold archive command — create a tarball of scaffolded files."""

import tarfile
import tempfile
from datetime import date
from pathlib import Path

import click

from display_lib.output import error, header, info, success
from lib.assembler import print_dry_run, print_report, scaffold_to_dir
from lib.paths import get_scaf_data_dir, require_source_repo
from lib.errors import EXIT_REFERENCE, EXIT_RUNTIME
from lib.manifest import (
    check_source_files,
    load_manifest,
    resolve_modules,
    validate_manifest,
)
from lib.validator import print_validation, validate_scaffold


@click.command()
@click.option(
    "--output",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Output directory for tarball",
)
@click.option("--no-github", is_flag=True, help="Exclude github module")
@click.option(
    "--no-backend-lib", is_flag=True, help="Exclude backend-lib shared library"
)
@click.option("--dry-run", "-n", is_flag=True, help="Show plan without creating")
def archive_cmd(output, no_github, no_backend_lib, dry_run):
    """Create a tarball of scaffolded AI infrastructure files."""
    source_repo = require_source_repo()
    scaf_data = get_scaf_data_dir()

    header("Scaffold Archive")

    # Load and validate manifest
    manifest = load_manifest(scaf_data / "manifest.json")
    validate_manifest(manifest, scaf_data / "schemas" / "manifest.schema.json")

    # Resolve modules
    modules = resolve_modules(
        manifest,
        include_github=not no_github,
        include_backend_lib=not no_backend_lib,
    )
    info(f"Modules: {', '.join(modules)}")

    # Pre-check: all source files exist
    missing = check_source_files(manifest, modules, source_repo)
    if missing:
        for f in missing:
            error(f"Missing source file: {f}")
        raise SystemExit(EXIT_REFERENCE)

    # Dry run
    if dry_run:
        print_dry_run(manifest, modules, source_repo)
        return

    # Scaffold into temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        report = scaffold_to_dir(manifest, modules, source_repo, tmp_path)

        # Validate
        results = validate_scaffold(manifest, modules, tmp_path)
        if not print_validation(results):
            raise SystemExit(EXIT_RUNTIME)

        # Create tarball
        today = date.today().isoformat()
        tarball_name = f"agentic-scaffold-{today}.tar.gz"
        tarball_path = Path(output) / tarball_name

        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(tmpdir, arcname="scaffold")

        success(f"Tarball created: {tarball_path}")
        print_report(report)
