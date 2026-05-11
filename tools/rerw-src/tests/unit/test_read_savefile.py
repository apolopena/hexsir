"""Tests for `rerw read savefile`."""

import struct
from pathlib import Path

from click.testing import CliRunner
from commands.read_savefile import read_savefile_cmd
from test_lib.cli import assert_cli_ok

REPO_ROOT = Path(__file__).resolve().parents[3].parent
PROOF_CH3 = (
    REPO_ROOT
    / "rw"
    / "saves"
    / "proofs"
    / "geppetto"
    / "chapter3"
    / "laser_lenses_1"
    / "Profile_1.ob"
)
PROOF_CLEAN = (
    REPO_ROOT / "rw" / "saves" / "proofs" / "geppetto" / "clean" / "Profile_1.ob"
)


def _make_synth_save(tmp_path: Path, *, chapter: int | None, level: int | None) -> Path:
    """Build a tiny save with optional chapter + level GUIDs."""
    chapter_guids = [
        bytes.fromhex("13fa8e2c314d88babb71a8e3c4df01"),
        bytes.fromhex("6661756c746465662e6f7426ba4519"),
    ]
    level_guid = bytes.fromhex("b5317efe6f4a95737325675793e600")

    body = bytearray(b"\x00" * 8)
    if chapter is not None:
        for g in chapter_guids:
            body.extend(g)
            body.extend(struct.pack("<i", chapter))
            body.extend(b"\x00" * 4)
    if level is not None:
        body.extend(level_guid)
        body.extend(struct.pack("<i", level))
        body.extend(b"\x00" * 4)

    header = bytearray(16)
    save = header + body
    p = tmp_path / "Profile_1.ob"
    p.write_bytes(save)
    return p


def test_help():
    runner = CliRunner()
    result = runner.invoke(read_savefile_cmd, ["--help"])
    assert_cli_ok(result)


def test_missing_source_errors():
    runner = CliRunner()
    result = runner.invoke(read_savefile_cmd, [])
    assert result.exit_code != 0


def test_no_flags_prints_all_fields(tmp_path: Path):
    save = _make_synth_save(tmp_path, chapter=2, level=8)
    runner = CliRunner()
    result = runner.invoke(read_savefile_cmd, ["--source", str(save)])
    assert_cli_ok(result)
    assert "Source savefile:" in result.output
    assert "chapter: 2" in result.output
    assert "level: 8" in result.output


def test_chapter_flag_prints_only_chapter(tmp_path: Path):
    save = _make_synth_save(tmp_path, chapter=2, level=8)
    runner = CliRunner()
    result = runner.invoke(read_savefile_cmd, ["--source", str(save), "--chapter"])
    assert_cli_ok(result)
    assert "chapter: 2" in result.output
    assert "level" not in result.output


def test_level_flag_prints_only_level(tmp_path: Path):
    save = _make_synth_save(tmp_path, chapter=2, level=8)
    runner = CliRunner()
    result = runner.invoke(read_savefile_cmd, ["--source", str(save), "--level"])
    assert_cli_ok(result)
    assert "level: 8" in result.output
    assert "chapter" not in result.output


def test_missing_chapter_field_reports_not_present(tmp_path: Path):
    """Synthetic clean save: no chapter GUIDs → '<not present>'."""
    save = _make_synth_save(tmp_path, chapter=None, level=1)
    runner = CliRunner()
    result = runner.invoke(read_savefile_cmd, ["--source", str(save)])
    assert_cli_ok(result)
    assert "chapter: <not present>" in result.output
    assert "level: 1" in result.output


def test_verbose_prints_load_summary(tmp_path: Path):
    save = _make_synth_save(tmp_path, chapter=2, level=8)
    runner = CliRunner()
    result = runner.invoke(read_savefile_cmd, ["--source", str(save), "-v"])
    assert_cli_ok(result)
    assert "Source savefile:" in result.output
    assert "bytes, CRC=0x" in result.output


# --- Tests against real proofs (skip cleanly if files aren't checked in) ---


def test_real_chapter3_proof_reads_chapter_2_level_8():
    if not PROOF_CH3.is_file():
        return  # proofs not present in this checkout
    runner = CliRunner()
    result = runner.invoke(read_savefile_cmd, ["--source", str(PROOF_CH3)])
    assert_cli_ok(result)
    assert "chapter: 2" in result.output
    assert "level: 8" in result.output


def test_real_clean_save_reports_chapter_not_present():
    if not PROOF_CLEAN.is_file():
        return  # proofs not present
    runner = CliRunner()
    result = runner.invoke(read_savefile_cmd, ["--source", str(PROOF_CLEAN)])
    assert_cli_ok(result)
    assert "chapter: <not present>" in result.output
