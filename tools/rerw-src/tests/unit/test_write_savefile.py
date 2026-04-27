"""Tests for `rerw write savefile`."""

import shutil
import struct
import zlib
from pathlib import Path

from click.testing import CliRunner
from commands.write_savefile import SAVE_FILENAME, write_savefile_cmd
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
GOLDEN_CH1 = (
    REPO_ROOT
    / "rw"
    / "saves"
    / "edits"
    / "golden"
    / "geppetto"
    / "chapter1"
    / "laser_lenses_1"
    / "chapter-rewind-from-ch3"
    / "Profile_1.ob"
)


def _make_synth_save(tmp_path: Path, *, chapter: int = 2, level: int = 8) -> Path:
    chapter_guids = [
        bytes.fromhex("13fa8e2c314d88babb71a8e3c4df01"),
        bytes.fromhex("6661756c746465662e6f7426ba4519"),
    ]
    level_guid = bytes.fromhex("b5317efe6f4a95737325675793e600")

    body = bytearray(b"\x00" * 8)
    for g in chapter_guids:
        body.extend(g)
        body.extend(struct.pack("<i", chapter))
        body.extend(b"\x00" * 4)
    body.extend(level_guid)
    body.extend(struct.pack("<i", level))
    body.extend(b"\x00" * 4)

    header = bytearray(16)
    # Stale CRC; we'll verify the tool replaces it correctly.
    header[12:16] = b"\xde\xad\xbe\xef"
    save = bytes(header + body)
    p = tmp_path / "src.ob"
    p.write_bytes(save)
    return p


def test_help():
    runner = CliRunner()
    result = runner.invoke(write_savefile_cmd, ["--help"])
    assert_cli_ok(result)


def test_no_field_flags_errors(tmp_path: Path):
    src = _make_synth_save(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        write_savefile_cmd, ["--source", str(src), "--dest", str(dest)]
    )
    assert result.exit_code != 0
    assert "No field flag" in result.output


def test_chapter_edit_writes_correct_crc(tmp_path: Path):
    src = _make_synth_save(tmp_path, chapter=2, level=8)
    dest = tmp_path / "out"
    dest.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        write_savefile_cmd,
        ["--source", str(src), "--dest", str(dest), "--chapter", "0", "--force"],
    )
    assert_cli_ok(result)
    out = dest / SAVE_FILENAME
    assert out.exists()
    blob = out.read_bytes()
    # Chapter is now 0 in both GUID locations.
    g_a = bytes.fromhex("13fa8e2c314d88babb71a8e3c4df01")
    g_b = bytes.fromhex("6661756c746465662e6f7426ba4519")
    pa = blob.find(g_a)
    pb = blob.find(g_b)
    assert struct.unpack("<i", blob[pa + 15 : pa + 19])[0] == 0
    assert struct.unpack("<i", blob[pb + 15 : pb + 19])[0] == 0
    # CRC matches body.
    expected_crc = zlib.crc32(blob[16:]) & 0xFFFFFFFF
    written_crc = struct.unpack("<I", blob[12:16])[0]
    assert written_crc == expected_crc
    # Output mentions transitions.
    assert "Source savefile:" in result.output
    assert "chapter: 2 -> 0" in result.output
    assert "CRC32:" in result.output


def test_atomic_multi_field_edit(tmp_path: Path):
    src = _make_synth_save(tmp_path, chapter=2, level=8)
    dest = tmp_path / "out"
    dest.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        write_savefile_cmd,
        [
            "--source",
            str(src),
            "--dest",
            str(dest),
            "--chapter",
            "1",
            "--level",
            "15",
            "--force",
        ],
    )
    assert_cli_ok(result)
    blob = (dest / SAVE_FILENAME).read_bytes()
    g_a = bytes.fromhex("13fa8e2c314d88babb71a8e3c4df01")
    g_l = bytes.fromhex("b5317efe6f4a95737325675793e600")
    pa = blob.find(g_a)
    pl = blob.find(g_l)
    assert struct.unpack("<i", blob[pa + 15 : pa + 19])[0] == 1
    assert struct.unpack("<i", blob[pl + 15 : pl + 19])[0] == 15
    expected_crc = zlib.crc32(blob[16:]) & 0xFFFFFFFF
    assert struct.unpack("<I", blob[12:16])[0] == expected_crc
    assert "chapter: 2 -> 1" in result.output
    assert "level: 8 -> 15" in result.output


def test_overwrite_prompt_default_aborts(tmp_path: Path):
    src = _make_synth_save(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    pre_existing = dest / SAVE_FILENAME
    pre_existing.write_bytes(b"existing")
    runner = CliRunner()
    # Send "n" to the prompt.
    result = runner.invoke(
        write_savefile_cmd,
        ["--source", str(src), "--dest", str(dest), "--chapter", "0"],
        input="n\n",
    )
    assert result.exit_code != 0
    # File untouched.
    assert pre_existing.read_bytes() == b"existing"


def test_force_skips_prompt(tmp_path: Path):
    src = _make_synth_save(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / SAVE_FILENAME).write_bytes(b"existing")
    runner = CliRunner()
    result = runner.invoke(
        write_savefile_cmd,
        ["--source", str(src), "--dest", str(dest), "--chapter", "0", "--force"],
    )
    assert_cli_ok(result)
    assert (dest / SAVE_FILENAME).read_bytes() != b"existing"


def test_dest_not_a_dir_errors(tmp_path: Path):
    src = _make_synth_save(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        write_savefile_cmd,
        [
            "--source",
            str(src),
            "--dest",
            str(tmp_path / "missing"),
            "--chapter",
            "0",
            "--force",
        ],
    )
    assert result.exit_code != 0


def test_field_not_present_errors(tmp_path: Path):
    """Editing chapter on a synthetic save with no chapter GUIDs errors."""
    # Make a save WITHOUT chapter GUIDs.
    body = bytearray(b"\x00" * 64)
    save = bytes(bytearray(16) + body)
    src = tmp_path / "no_chapter.ob"
    src.write_bytes(save)
    dest = tmp_path / "out"
    dest.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        write_savefile_cmd,
        ["--source", str(src), "--dest", str(dest), "--chapter", "0", "--force"],
    )
    assert result.exit_code != 0
    assert "not present" in result.output


def test_verbose_emits_per_guid_detail(tmp_path: Path):
    src = _make_synth_save(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        write_savefile_cmd,
        [
            "--source",
            str(src),
            "--dest",
            str(dest),
            "--chapter",
            "0",
            "--force",
            "-v",
        ],
    )
    assert_cli_ok(result)
    assert "Source savefile:" in result.output
    assert "bytes, CRC=0x" in result.output
    assert "Field: chapter" in result.output
    assert "GUID 13fa8e2c" in result.output


# --- Golden-file regression ---


def test_chapter_rewind_matches_golden(tmp_path: Path):
    """End-to-end: edit ch3 → ch1 (chapter=0) reproduces the verified golden."""
    if not PROOF_CH3.is_file() or not GOLDEN_CH1.is_file():
        return  # proofs/golden not in this checkout
    # Copy the proof so the test never mutates the checked-in file.
    src = tmp_path / "src.ob"
    shutil.copy2(PROOF_CH3, src)
    dest = tmp_path / "out"
    dest.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        write_savefile_cmd,
        ["--source", str(src), "--dest", str(dest), "--chapter", "0", "--force"],
    )
    assert_cli_ok(result)

    actual = (dest / SAVE_FILENAME).read_bytes()
    expected = GOLDEN_CH1.read_bytes()
    assert actual == expected, (
        "Chapter-rewind output diverges from the verified golden. "
        f"Sizes: actual={len(actual)} expected={len(expected)}"
    )
