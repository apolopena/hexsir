"""Tests for lib.save_fields YAML loader."""

from pathlib import Path

import pytest
from lib.save_fields import (
    Field,
    SaveFieldsError,
    default_registry_path,
    load_fields,
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "save-fields.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_default_registry_loads():
    """The bundled registry parses cleanly."""
    fields = load_fields(default_registry_path())
    assert "chapter" in fields
    assert "level" in fields
    chapter = fields["chapter"]
    assert isinstance(chapter, Field)
    assert chapter.category == "scalar"
    assert chapter.type == "int32_le"
    assert len(chapter.guids) == 2
    assert all(len(g) == 15 for g in chapter.guids)
    assert fields["level"].guids[0].hex() == "b5317efe6f4a95737325675793e600"


def test_missing_file(tmp_path: Path):
    with pytest.raises(SaveFieldsError, match="not found"):
        load_fields(tmp_path / "nope.yaml")


def test_empty_file(tmp_path: Path):
    p = _write(tmp_path, "")
    with pytest.raises(SaveFieldsError, match="empty"):
        load_fields(p)


def test_top_level_not_mapping(tmp_path: Path):
    p = _write(tmp_path, "- a\n- b\n")
    with pytest.raises(SaveFieldsError, match="mapping"):
        load_fields(p)


def test_bad_yaml(tmp_path: Path):
    p = _write(tmp_path, "scalar:\n  chapter: [unterminated")
    with pytest.raises(SaveFieldsError, match="YAML parse error"):
        load_fields(p)


def test_missing_keys(tmp_path: Path):
    p = _write(tmp_path, "scalar:\n  chapter:\n    type: int32_le\n")
    with pytest.raises(SaveFieldsError, match="missing required key"):
        load_fields(p)


def test_unsupported_type(tmp_path: Path):
    p = _write(
        tmp_path,
        "scalar:\n  x:\n    type: float64_be\n    guids:\n      - "
        + "00" * 15
        + "\n",
    )
    with pytest.raises(SaveFieldsError, match="unsupported type"):
        load_fields(p)


def test_bad_guid_hex(tmp_path: Path):
    p = _write(
        tmp_path,
        "scalar:\n  x:\n    type: int32_le\n    guids:\n      - notvalidhex\n",
    )
    with pytest.raises(SaveFieldsError, match="not valid hex"):
        load_fields(p)


def test_wrong_guid_length(tmp_path: Path):
    # 14 bytes (28 hex) instead of 15
    p = _write(
        tmp_path,
        "scalar:\n  x:\n    type: int32_le\n    guids:\n      - " + "ab" * 14 + "\n",
    )
    with pytest.raises(SaveFieldsError, match="15 bytes"):
        load_fields(p)


def test_empty_guid_list(tmp_path: Path):
    p = _write(tmp_path, "scalar:\n  x:\n    type: int32_le\n    guids: []\n")
    with pytest.raises(SaveFieldsError, match="non-empty"):
        load_fields(p)


def test_wrong_type_for_type_field(tmp_path: Path):
    p = _write(
        tmp_path,
        "scalar:\n  x:\n    type: 42\n    guids:\n      - " + "ab" * 15 + "\n",
    )
    with pytest.raises(SaveFieldsError, match="type must be a string"):
        load_fields(p)


def test_duplicate_field_name_across_categories(tmp_path: Path):
    body = (
        "scalar:\n"
        "  shared:\n"
        "    type: int32_le\n"
        "    guids:\n      - " + "ab" * 15 + "\n"
        "array:\n"
        "  shared:\n"
        "    type: int32_le\n"
        "    guids:\n      - " + "cd" * 15 + "\n"
    )
    p = _write(tmp_path, body)
    with pytest.raises(SaveFieldsError, match="Duplicate field name"):
        load_fields(p)


def test_reserved_empty_category_allowed(tmp_path: Path):
    """A `category:` line with no body (e.g. `array:`) is allowed."""
    body = (
        "scalar:\n"
        "  x:\n"
        "    type: int32_le\n"
        "    guids:\n      - " + "ab" * 15 + "\n"
        "array:\n"
    )
    p = _write(tmp_path, body)
    fields = load_fields(p)
    assert "x" in fields
