"""Strict-key registry views over bundled game-asset YAML files.

Three registries:
  - heroes:         data/heroes/<key>.yaml — one file per hero (12 today)
  - hero_talents:   data/heroes/<key>.yaml controllers list (28 per hero)
  - magical_items:  data/magical-items.yaml items list (68 today)

Lookup is strict: keys must match `hero.key` / `controllers[].key` /
`items[].key` exactly. No alias matching, no display-name fallback, no
fuzzy normalization. Discovery is via `rerw game-assets inspect`.

Schema validation is light — registry files declare:
  schema_version: "1.0.0"
  registry_id: hero_talents | magical_items
The loader rejects mismatched registry_id and rejects schema_version with
a different major version (forward-compatible within major 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

GUID_LEN_16 = 16

# Major version compatibility: each registry accepts schema_version with the
# expected major version. Minor/patch within that major is forward-compatible.
EXPECTED_SCHEMA_MAJOR = {
    "hero_talents": 1,
    "magical_items": 1,
}


class RegistryError(ValueError):
    """Raised when a bundled registry is malformed or a strict key is absent."""


@dataclass(frozen=True)
class HeroEntry:
    """A hero entry derived from data/heroes/<key>.yaml."""

    key: str
    display_name: str
    engine_name: str
    save_ref: str
    yaml_path: Path


@dataclass(frozen=True)
class TalentEntry:
    """A talent entry from data/heroes/<hero>.yaml controllers list."""

    hero_key: str
    key: str
    display_name: str
    controller_name: str
    guid: bytes
    desc: str
    is_start: bool
    is_ult: bool
    ult_upgrade_for: str | None


@dataclass(frozen=True)
class MagicalItemEntry:
    """A magical-object entry from data/magical-items.yaml."""

    key: str
    display_name: str
    effect: str
    guid: bytes
    rarity: str
    desc: str


@dataclass(frozen=True)
class HeroRegistry:
    """Hero lookup by public key or by engine name."""

    entries: dict[str, HeroEntry]
    by_engine_name: dict[str, HeroEntry]

    def lookup(self, key: str) -> HeroEntry:
        """Return a hero by exact public key, or raise."""
        try:
            return self.entries[key]
        except KeyError as exc:
            valid = ", ".join(sorted(self.entries)) or "<none>"
            raise RegistryError(
                f"Unknown hero key: {key!r}. "
                f"Run `rerw game-assets inspect heroes` for valid keys "
                f"({valid})."
            ) from exc

    def lookup_by_engine_name(self, engine_name: str) -> HeroEntry:
        """Return a hero by the engine token from save paths, or raise."""
        try:
            return self.by_engine_name[engine_name]
        except KeyError as exc:
            raise RegistryError(
                f"Unknown hero engine name: {engine_name!r}"
            ) from exc


@dataclass(frozen=True)
class TalentRegistry:
    """Talent lookup for one hero."""

    hero_key: str
    entries: dict[str, TalentEntry]

    def lookup(self, key: str) -> TalentEntry:
        """Return a talent by exact key within this hero, or raise."""
        try:
            return self.entries[key]
        except KeyError as exc:
            raise RegistryError(
                f"Unknown talent key {key!r} for hero {self.hero_key!r}. "
                f"Run `rerw game-assets inspect talents --for-hero "
                f"{self.hero_key}` for valid keys."
            ) from exc


@dataclass(frozen=True)
class MagicalItemRegistry:
    """Magical-item lookup."""

    entries: dict[str, MagicalItemEntry]

    def lookup(self, key: str) -> MagicalItemEntry:
        """Return a magical item by exact key, or raise."""
        try:
            return self.entries[key]
        except KeyError as exc:
            raise RegistryError(
                f"Unknown item key: {key!r}. "
                f"Run `rerw game-assets inspect items` for valid keys."
            ) from exc


# --- Loading --------------------------------------------------------------


def default_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RegistryError(f"Registry file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise RegistryError(f"{path}: top-level must be a mapping")
    return raw


def _check_schema(raw: dict, *, path: Path, expected_registry_id: str) -> None:
    """Validate schema_version (major-version match) and registry_id."""
    registry_id = raw.get("registry_id")
    if registry_id != expected_registry_id:
        raise RegistryError(
            f"{path}: registry_id must be {expected_registry_id!r}, "
            f"got {registry_id!r}"
        )
    raw_version = raw.get("schema_version")
    if not isinstance(raw_version, str):
        raise RegistryError(
            f"{path}: schema_version must be a SemVer string, got {raw_version!r}"
        )
    parts = raw_version.split(".")
    if len(parts) < 1 or not parts[0].isdigit():
        raise RegistryError(
            f"{path}: schema_version {raw_version!r} is not a valid SemVer"
        )
    major = int(parts[0])
    expected = EXPECTED_SCHEMA_MAJOR[expected_registry_id]
    if major != expected:
        raise RegistryError(
            f"{path}: schema_version {raw_version} has major {major}; "
            f"this loader supports major {expected}"
        )


def _parse_guid(path: Path, label: str, raw: object) -> bytes:
    if not isinstance(raw, str):
        raise RegistryError(f"{path}: {label}.guid must be a string")
    try:
        guid = bytes.fromhex(raw)
    except ValueError as exc:
        raise RegistryError(
            f"{path}: {label}.guid is not valid hex: {raw!r}"
        ) from exc
    if len(guid) != GUID_LEN_16:
        raise RegistryError(
            f"{path}: {label}.guid must be {GUID_LEN_16} bytes, got {len(guid)}"
        )
    return guid


def _require_string(path: Path, label: str, raw: object) -> str:
    if not isinstance(raw, str) or not raw:
        raise RegistryError(f"{path}: {label} must be a non-empty string")
    return raw


def heroes(data_dir: Path | None = None) -> HeroRegistry:
    """Load all hero entries from data/heroes/*.yaml keyed by hero.key."""
    root = (data_dir or default_data_dir()) / "heroes"
    if not root.is_dir():
        raise RegistryError(f"Heroes directory not found: {root}")

    by_key: dict[str, HeroEntry] = {}
    by_engine_name: dict[str, HeroEntry] = {}
    for path in sorted(root.glob("*.yaml")):
        raw = _read_yaml(path)
        _check_schema(raw, path=path, expected_registry_id="hero_talents")
        hero = raw.get("hero")
        if not isinstance(hero, dict):
            raise RegistryError(f"{path}: top-level 'hero' mapping is required")
        key = _require_string(path, "hero.key", hero.get("key"))
        if key != path.stem:
            raise RegistryError(
                f"{path}: hero.key {key!r} must match filename stem {path.stem!r}"
            )
        if key in by_key:
            raise RegistryError(f"{path}: duplicate hero key {key!r}")
        engine_name = _require_string(
            path, "hero.engine_name", hero.get("engine_name")
        )
        if engine_name in by_engine_name:
            raise RegistryError(
                f"{path}: duplicate hero.engine_name {engine_name!r}"
            )
        entry = HeroEntry(
            key=key,
            display_name=engine_name.replace("_", " "),
            engine_name=engine_name,
            save_ref=f"Heroes\\{engine_name}.herodef.ot",
            yaml_path=path,
        )
        by_key[key] = entry
        by_engine_name[engine_name] = entry

    if not by_key:
        raise RegistryError(f"No hero YAML files found under {root}")
    return HeroRegistry(entries=by_key, by_engine_name=by_engine_name)


def hero_talents(
    hero_key: str, data_dir: Path | None = None
) -> TalentRegistry:
    """Load one hero's talent entries from data/heroes/<key>.yaml controllers."""
    hero = heroes(data_dir).lookup(hero_key)
    raw = _read_yaml(hero.yaml_path)
    _check_schema(raw, path=hero.yaml_path, expected_registry_id="hero_talents")
    controllers = raw.get("controllers")
    if not isinstance(controllers, list):
        raise RegistryError(f"{hero.yaml_path}: 'controllers' must be a list")

    by_key: dict[str, TalentEntry] = {}
    seen_guids: dict[bytes, str] = {}
    for index, entry in enumerate(controllers):
        if not isinstance(entry, dict):
            raise RegistryError(
                f"{hero.yaml_path}: controllers[{index}] must be a mapping"
            )
        label = f"controllers[{index}]"
        key = _require_string(hero.yaml_path, f"{label}.key", entry.get("key"))
        if key in by_key:
            raise RegistryError(
                f"{hero.yaml_path}: duplicate talent key {key!r}"
            )
        display_name = _require_string(
            hero.yaml_path, f"{label}.display_name", entry.get("display_name")
        )
        controller_name = _require_string(
            hero.yaml_path,
            f"{label}.controller_name",
            entry.get("controller_name"),
        )
        guid = _parse_guid(hero.yaml_path, f"{label}({key})", entry.get("guid"))
        if guid in seen_guids:
            raise RegistryError(
                f"{hero.yaml_path}: duplicate talent guid {guid.hex()} for "
                f"{seen_guids[guid]!r} and {key!r}"
            )
        seen_guids[guid] = key
        by_key[key] = TalentEntry(
            hero_key=hero_key,
            key=key,
            display_name=display_name,
            controller_name=controller_name,
            guid=guid,
            desc=str(entry.get("desc") or "").strip(),
            is_start=bool(entry.get("is_start", False)),
            is_ult=bool(entry.get("is_ult", False)),
            ult_upgrade_for=entry.get("ult_upgrade_for"),
        )
    return TalentRegistry(hero_key=hero_key, entries=by_key)


def magical_items(data_dir: Path | None = None) -> MagicalItemRegistry:
    """Load magical-object entries from data/magical-items.yaml."""
    path = (data_dir or default_data_dir()) / "magical-items.yaml"
    raw = _read_yaml(path)
    _check_schema(raw, path=path, expected_registry_id="magical_items")
    items_raw = raw.get("items")
    if not isinstance(items_raw, list):
        raise RegistryError(f"{path}: 'items' must be a list")

    by_key: dict[str, MagicalItemEntry] = {}
    seen_guids: dict[bytes, str] = {}
    for index, entry in enumerate(items_raw):
        if not isinstance(entry, dict):
            raise RegistryError(f"{path}: items[{index}] must be a mapping")
        label = f"items[{index}]"
        key = _require_string(path, f"{label}.key", entry.get("key"))
        if key in by_key:
            raise RegistryError(f"{path}: duplicate item key {key!r}")
        guid = _parse_guid(path, f"{label}({key})", entry.get("guid"))
        if guid in seen_guids:
            raise RegistryError(
                f"{path}: duplicate item guid {guid.hex()} for "
                f"{seen_guids[guid]!r} and {key!r}"
            )
        seen_guids[guid] = key
        by_key[key] = MagicalItemEntry(
            key=key,
            display_name=str(entry.get("display_name") or ""),
            effect=str(entry.get("effect") or ""),
            guid=guid,
            rarity=str(entry.get("rarity") or ""),
            desc=str(entry.get("desc") or "").strip(),
        )
    return MagicalItemRegistry(entries=by_key)
