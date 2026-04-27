"""Save-field registry loader.

Reads `data/save-fields.yaml` into typed `Field` objects. The registry maps
human-friendly field names (e.g. "chapter", "level") to their binary layout
(value type + one or more 15-byte GUIDs that locate the value in the save).

The CLI flags (`--chapter`, `--level`) are wired to fields by name in the
command modules — adding a new YAML entry does NOT auto-expose a flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# Currently the only supported value type. Future types (e.g. float32_le,
# string, array) should be added here and in `save_edit.py`.
# TODO: extend to non-int32 value types as they're identified.
SUPPORTED_TYPES = frozenset({"int32_le"})

GUID_LEN = 15


@dataclass(frozen=True)
class Field:
    """A registered save-file field.

    Attributes:
        name: Field identifier (e.g. "chapter").
        category: Top-level grouping (e.g. "scalar").
        type: Binary value type — currently only "int32_le".
        guids: 15-byte GUIDs that locate the value. When more than one is
            present, all are written in lockstep on edit.
        description: Free-form notes from the YAML.
    """

    name: str
    category: str
    type: str
    guids: tuple[bytes, ...]
    description: str


class SaveFieldsError(ValueError):
    """Raised when the YAML registry is malformed."""


def default_registry_path() -> Path:
    """Path to the bundled `save-fields.yaml`."""
    return Path(__file__).resolve().parent.parent / "data" / "save-fields.yaml"


def _parse_guid(raw: object, *, field_name: str, index: int) -> bytes:
    if not isinstance(raw, str):
        raise SaveFieldsError(
            f"Field '{field_name}': guids[{index}] must be a hex string, "
            f"got {type(raw).__name__}"
        )
    try:
        guid = bytes.fromhex(raw)
    except ValueError as exc:
        raise SaveFieldsError(
            f"Field '{field_name}': guids[{index}] is not valid hex: {raw!r}"
        ) from exc
    if len(guid) != GUID_LEN:
        raise SaveFieldsError(
            f"Field '{field_name}': guids[{index}] must be {GUID_LEN} bytes "
            f"({GUID_LEN * 2} hex chars), got {len(guid)} bytes"
        )
    return guid


def _parse_field(name: str, category: str, body: object) -> Field:
    if not isinstance(body, dict):
        raise SaveFieldsError(
            f"Field '{name}': body must be a mapping, got {type(body).__name__}"
        )
    missing = {"type", "guids"} - set(body.keys())
    if missing:
        raise SaveFieldsError(
            f"Field '{name}': missing required key(s): {sorted(missing)}"
        )

    vtype = body["type"]
    if not isinstance(vtype, str):
        raise SaveFieldsError(
            f"Field '{name}': type must be a string, got {type(vtype).__name__}"
        )
    if vtype not in SUPPORTED_TYPES:
        raise SaveFieldsError(
            f"Field '{name}': unsupported type {vtype!r} "
            f"(supported: {sorted(SUPPORTED_TYPES)})"
        )

    guids_raw = body["guids"]
    if not isinstance(guids_raw, list) or not guids_raw:
        raise SaveFieldsError(f"Field '{name}': guids must be a non-empty list")
    guids = tuple(
        _parse_guid(g, field_name=name, index=i) for i, g in enumerate(guids_raw)
    )

    description = body.get("description", "") or ""
    if not isinstance(description, str):
        raise SaveFieldsError(
            f"Field '{name}': description must be a string when present"
        )

    return Field(
        name=name,
        category=category,
        type=vtype,
        guids=guids,
        description=description.strip(),
    )


def load_fields(path: Path | None = None) -> dict[str, Field]:
    """Load the save-field registry from YAML.

    Returns a dict keyed by field name. Categories are flattened — names are
    expected to be unique across categories (we raise if that's violated).
    """
    if path is None:
        path = default_registry_path()
    if not path.is_file():
        raise SaveFieldsError(f"Registry file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise SaveFieldsError(f"YAML parse error in {path}: {exc}") from exc

    if raw is None:
        raise SaveFieldsError(f"Registry file is empty: {path}")
    if not isinstance(raw, dict):
        raise SaveFieldsError(
            f"Top-level YAML must be a mapping, got {type(raw).__name__}"
        )

    fields: dict[str, Field] = {}
    for category, body in raw.items():
        if body is None:
            # Reserved-but-empty categories (e.g. `array:`) are allowed.
            continue
        if not isinstance(body, dict):
            raise SaveFieldsError(
                f"Category '{category}': body must be a mapping, "
                f"got {type(body).__name__}"
            )
        for name, fbody in body.items():
            if name in fields:
                raise SaveFieldsError(
                    f"Duplicate field name across categories: {name!r}"
                )
            fields[name] = _parse_field(name, category, fbody)

    return fields
