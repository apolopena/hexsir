"""Per-hero skill-controller registry loader.

Reads `data/heroes/<hero>.yaml` and provides name/alias → 16-byte GUID lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

import yaml

GUID_LEN_16 = 16


@dataclass(frozen=True)
class SkillController:
    """A single skill controller entry from a hero's herodef registry."""

    name: str
    guid: bytes
    aliases: tuple[str, ...]
    is_ult: bool


class SkillControllerError(ValueError):
    """Raised on malformed hero skill-controller YAML."""


def default_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


_CANONICAL_PREFIX = "skillcontroller"


def _normalize(name: str) -> str:
    """Case-insensitive lookup key with whitespace/punct collapsed.

    Strips the canonical "Skill Controller " prefix so users can type either
    "Skill Controller Trait Twins" or just "Trait Twins". Also handles
    "twin_dummies", "Twin-Dummies", "TwinDummies", etc. — the resolver
    keys on this normalized form, so a single alias entry covers every
    common punctuation/case variant.
    """
    raw = "".join(c for c in name.lower() if c.isalnum())
    if raw.startswith(_CANONICAL_PREFIX):
        raw = raw[len(_CANONICAL_PREFIX):]
    return raw


def _clean_aliases(
    raw_aliases: list, *, canonical_name: str, controller_label: str
) -> tuple[str, ...]:
    """Defensively normalize a YAML `aliases` list.

    Helper-friendliness: a hand-edited YAML may contain stray whitespace,
    accidental empty strings, duplicates, or aliases that already match the
    canonical name (redundant since the canonical is always indexed). This
    function turns any of that into a clean ordered tuple ready for indexing.

    Rules:
      - skip None / non-string entries (raise on non-string)
      - strip leading/trailing whitespace
      - skip empty / whitespace-only entries
      - skip aliases whose normalized form is empty (e.g. "!!!")
      - skip aliases redundant with the canonical name (same normalized key)
      - deduplicate (preserving first-seen order — first alias is the one
        the read command displays as the player-facing name)
    """
    seen_keys: set[str] = {_normalize(canonical_name)}
    out: list[str] = []
    for raw in raw_aliases:
        if raw is None:
            continue
        if not isinstance(raw, str):
            raise SkillControllerError(
                f"{controller_label}: alias must be a string, "
                f"got {type(raw).__name__}: {raw!r}"
            )
        s = raw.strip()
        if not s:
            continue
        k = _normalize(s)
        if not k:
            continue  # alias normalizes to empty, e.g. "!!!" or "---"
        if k in seen_keys:
            continue  # duplicate (or redundant with canonical name)
        seen_keys.add(k)
        out.append(s)
    return tuple(out)


def load_hero_controllers(rel_path: str | Path) -> dict[str, SkillController]:
    """Load a hero's skill-controller YAML, returning name/alias → entry.

    Keys include both the canonical name and every alias, all normalized.
    Aliases are defensively cleaned at load time (whitespace stripped, empties
    skipped, duplicates collapsed) so hand-edited YAMLs are robust.
    """
    data_dir = default_data_dir()
    path = (data_dir / rel_path).resolve() if not Path(rel_path).is_absolute() else Path(rel_path)
    if not path.is_file():
        raise SkillControllerError(f"Hero skill file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise SkillControllerError(f"{path}: top-level must be a mapping")
    controllers_raw = raw.get("controllers")
    if not isinstance(controllers_raw, list):
        raise SkillControllerError(f"{path}: 'controllers' must be a list")

    by_key: dict[str, SkillController] = {}
    for i, entry in enumerate(controllers_raw):
        if not isinstance(entry, dict):
            raise SkillControllerError(f"{path}: controllers[{i}] must be a mapping")
        name = entry.get("name")
        guid_hex = entry.get("guid")
        if not isinstance(name, str) or not isinstance(guid_hex, str):
            raise SkillControllerError(
                f"{path}: controllers[{i}] requires string 'name' and 'guid'"
            )
        try:
            guid = bytes.fromhex(guid_hex)
        except ValueError as exc:
            raise SkillControllerError(
                f"{path}: controllers[{i}] guid not valid hex: {guid_hex!r}"
            ) from exc
        if len(guid) != GUID_LEN_16:
            raise SkillControllerError(
                f"{path}: controllers[{i}] guid must be {GUID_LEN_16} bytes "
                f"({GUID_LEN_16 * 2} hex chars), got {len(guid)}"
            )
        aliases_raw = entry.get("aliases", []) or []
        if not isinstance(aliases_raw, list):
            raise SkillControllerError(
                f"{path}: controllers[{i}] 'aliases' must be a list"
            )
        is_ult = bool(entry.get("is_ult", False))
        clean_aliases = _clean_aliases(
            aliases_raw,
            canonical_name=name,
            controller_label=f"{path}: controllers[{i}] ({name!r})",
        )

        sc = SkillController(
            name=name,
            guid=guid,
            aliases=clean_aliases,
            is_ult=is_ult,
        )

        for key_source in (name, *sc.aliases):
            k = _normalize(key_source)
            if k in by_key and by_key[k].guid != guid:
                raise SkillControllerError(
                    f"{path}: alias collision for {key_source!r} between "
                    f"{by_key[k].name!r} and {name!r}"
                )
            by_key[k] = sc

    return by_key


def resolve_talent_id(
    controllers: dict[str, SkillController], identifier: str
) -> SkillController:
    """Resolve a name / alias / hex-guid string to a SkillController entry.

    Hex GUIDs (32 chars, all hex) bypass the name table and are returned as
    a synthetic SkillController. This lets users address controllers that
    aren't yet registered in the YAML.
    """
    s = identifier.strip()
    # Try as hex GUID first (32 hex chars)
    if len(s) == GUID_LEN_16 * 2:
        try:
            guid = bytes.fromhex(s)
            return SkillController(
                name=f"<raw guid {s}>",
                guid=guid,
                aliases=(),
                is_ult=False,
            )
        except ValueError:
            pass
    key = _normalize(s)
    if key not in controllers:
        # Suggest closest matches for diagnostics
        sample = sorted({c.name for c in controllers.values()})[:5]
        raise SkillControllerError(
            f"Unknown talent {identifier!r}. "
            f"Try a name or alias from the registry (e.g. {sample!r}) "
            f"or a 32-hex-char GUID."
        )
    return controllers[key]
